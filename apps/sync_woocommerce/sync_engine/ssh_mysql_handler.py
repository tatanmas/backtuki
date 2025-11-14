"""
Handler MySQL a través de SSH sin túnel
Ejecuta comandos MySQL directamente en el servidor remoto
"""

import logging
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
from .ssh_connection import SSHTunnel
from .django_config import get_sync_config

logger = logging.getLogger(__name__)

class SSHMySQLError(Exception):
    """Excepción personalizada para errores de MySQL vía SSH"""
    pass

class SSHMySQLHandler:
    """
    Handler MySQL que ejecuta comandos directamente en el servidor remoto vía SSH
    No requiere túnel, más simple y confiable para servidores compartidos
    """
    
    def __init__(self, ssh_config=None, mysql_config=None):
        self.ssh_tunnel: Optional[SSHTunnel] = None
        self.is_connected = False
        
        # Obtener configuración de Django si no se proporciona
        if ssh_config is None or mysql_config is None:
            sync_config = get_sync_config()
            self.ssh_config = ssh_config or sync_config.ssh
            self.mysql_config = mysql_config or sync_config.mysql
        else:
            self.ssh_config = ssh_config
            self.mysql_config = mysql_config
    
    def connect(self) -> bool:
        """
        Establece conexión SSH
        
        Returns:
            bool: True si la conexión fue exitosa
        """
        try:
            self.ssh_tunnel = SSHTunnel(self.ssh_config)
            if self.ssh_tunnel.connect():
                self.is_connected = True
                logger.info("Conexión SSH para MySQL establecida")
                return True
            else:
                logger.error("No se pudo establecer conexión SSH")
                return False
        except Exception as e:
            logger.error(f"Error conectando SSH: {e}")
            return False
    
    def disconnect(self):
        """Cierra la conexión SSH"""
        if self.ssh_tunnel:
            try:
                self.ssh_tunnel.disconnect()
                logger.info("Conexión SSH cerrada")
            except Exception as e:
                logger.error(f"Error cerrando conexión SSH: {e}")
            finally:
                self.ssh_tunnel = None
                self.is_connected = False
    
    def _ensure_connection(self) -> bool:
        """
        Asegura que hay una conexión SSH activa, reconectando si es necesario
        
        Returns:
            bool: True si la conexión está activa
        """
        # Verificar si la conexión existe y está activa
        if self.ssh_tunnel and self.is_connected:
            try:
                # Usar la nueva verificación mejorada
                if self.ssh_tunnel.is_connection_alive():
                    return True
                else:
                    logger.warning("Conexión SSH no está activa, reconectando...")
            except Exception as e:
                logger.warning(f"Error verificando conexión SSH: {e}, reconectando...")
        
        # Si llegamos aquí, necesitamos reconectar
        logger.info("Estableciendo nueva conexión SSH...")
        self.disconnect()  # Limpiar conexión anterior si existe
        return self.connect()
    
    def execute_mysql_query(self, query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        """
        Ejecuta una query MySQL en el servidor remoto con reconexión automática
        
        Args:
            query: Query SQL a ejecutar
            params: Parámetros para la query (se insertan con format)
            
        Returns:
            List[Dict]: Resultados de la query
        """
        # Asegurar conexión activa con reintentos
        max_connection_attempts = 3
        for attempt in range(max_connection_attempts):
            if self._ensure_connection():
                break
            
            if attempt < max_connection_attempts - 1:
                logger.warning(f"Intento de conexión {attempt + 1} falló, reintentando...")
                time.sleep(2)
            else:
                raise SSHMySQLError("No se pudo establecer conexión SSH después de múltiples intentos")
        
        # Ejecutar query con reintentos en caso de error de conexión
        max_query_attempts = 2
        last_error = None
        
        for query_attempt in range(max_query_attempts):
            try:
                # Preparar la query con parámetros si los hay
                if params:
                    # Escapar parámetros básicamente (para producción usar prepared statements)
                    escaped_params = []
                    for param in params:
                        if isinstance(param, str):
                            escaped_param = param.replace("'", "\\'")
                            escaped_params.append("'" + escaped_param + "'")
                        else:
                            escaped_params.append(str(param))
                    formatted_query = query % tuple(escaped_params)
                else:
                    formatted_query = query
            
                # Construir comando MySQL usando heredoc para evitar problemas de escape
                # Usar un delimitador único para heredoc
                delimiter = "EOF_MYSQL_QUERY"
                
                mysql_cmd = f"""mysql -h {self.mysql_config.host} -u {self.mysql_config.username} -p'{self.mysql_config.password}' -D {self.mysql_config.database} --batch --raw --skip-column-names << '{delimiter}'
{formatted_query}
{delimiter}"""
                
                logger.debug(f"Ejecutando MySQL query: {formatted_query[:100]}...")
                
                start_time = time.time()
                stdout, stderr, exit_code = self.ssh_tunnel.execute_command(mysql_cmd)
                execution_time = time.time() - start_time
                
                if exit_code != 0:
                    error_msg = stderr.strip() if stderr.strip() else "Error desconocido en MySQL"
                    raise SSHMySQLError(f"Error en query MySQL: {error_msg}")
                
                # Parsear resultados
                results = self._parse_mysql_output(stdout, formatted_query)
                
                logger.info(f"Query ejecutada en {execution_time:.2f}s, {len(results)} resultados")
                return results
                
            except (SSHMySQLError, Exception) as e:
                last_error = e
                logger.error(f"Error ejecutando query MySQL (intento {query_attempt + 1}): {e}")
                
                # Si es el primer intento y el error parece ser de conexión, intentar reconectar
                if query_attempt == 0 and ("SSH" in str(e) or "Connection" in str(e) or "Broken pipe" in str(e)):
                    logger.warning("Error de conexión detectado, forzando reconexión...")
                    self.disconnect()
                    if not self._ensure_connection():
                        break  # Si no podemos reconectar, no tiene sentido reintentar
                    continue
                else:
                    break  # Para otros errores o segundo intento, no reintentar
        
        # Si llegamos aquí, todos los intentos fallaron
        raise SSHMySQLError(f"Error en query después de {max_query_attempts} intentos: {last_error}")
    
    def _parse_mysql_output(self, output: str, query: str) -> List[Dict[str, Any]]:
        """
        Parsea la salida de MySQL en formato batch
        
        Args:
            output: Salida del comando MySQL
            query: Query original para determinar columnas
            
        Returns:
            List[Dict]: Resultados parseados
        """
        if not output.strip():
            return []
        
        lines = output.strip().split('\n')
        
        # Para queries SELECT, necesitamos obtener los nombres de columnas
        # Como usamos --skip-column-names, tenemos que inferirlos de la query
        column_names = self._extract_column_names_from_query(query)
        
        results = []
        for line in lines:
            if line.strip():
                # Dividir por tabs (formato batch de MySQL)
                values = line.split('\t')
                
                # Crear diccionario con nombres de columnas
                if len(column_names) == len(values):
                    row_dict = {}
                    for i, col_name in enumerate(column_names):
                        value = values[i]
                        # Convertir nombre de columna a minúsculas para consistencia
                        col_name_lower = col_name.lower()
                        # Convertir NULL a None
                        if value == 'NULL' or value == '\\N':
                            row_dict[col_name_lower] = None
                        else:
                            row_dict[col_name_lower] = value
                    results.append(row_dict)
                else:
                    # Si no coinciden las columnas, usar índices genéricos
                    row_dict = {}
                    for i, value in enumerate(values):
                        col_name = column_names[i] if i < len(column_names) else f'col_{i}'
                        col_name_lower = col_name.lower()
                        if value == 'NULL' or value == '\\N':
                            row_dict[col_name_lower] = None
                        else:
                            row_dict[col_name_lower] = value
                    results.append(row_dict)
        
        return results
    
    def _extract_column_names_from_query(self, query: str) -> List[str]:
        """
        Extrae nombres de columnas de una query SELECT
        Implementación básica - en producción usar parser SQL más robusto
        """
        query_upper = query.upper().strip()
        
        if not query_upper.startswith('SELECT'):
            return ['result']  # Para queries no-SELECT
        
        try:
            # Buscar la parte SELECT ... FROM
            select_part = query_upper.split('FROM')[0].replace('SELECT', '').strip()
            
            # Dividir por comas y limpiar
            columns = []
            for col in select_part.split(','):
                col = col.strip()
                
                # Manejar alias (AS)
                if ' AS ' in col:
                    col = col.split(' AS ')[1].strip()
                # Manejar alias sin AS
                elif ' ' in col and not any(func in col for func in ['MAX(', 'MIN(', 'COUNT(', 'SUM(', 'AVG(', 'CASE']):
                    parts = col.split()
                    col = parts[-1]  # Tomar la última parte como alias
                
                # Limpiar caracteres especiales
                col = col.replace('`', '').replace("'", '').replace('"', '')
                
                # Si es una función o expresión compleja, usar nombre genérico
                if '(' in col or ')' in col:
                    if 'MAX(' in col.upper():
                        col = col.replace('MAX(', '').replace(')', '')
                    elif 'MIN(' in col.upper():
                        col = col.replace('MIN(', '').replace(')', '')
                    elif 'COUNT(' in col.upper():
                        col = 'count'
                    elif 'SUM(' in col.upper():
                        col = col.replace('SUM(', '').replace(')', '') + '_sum'
                    else:
                        col = f'expr_{len(columns)}'
                
                columns.append(col)
            
            return columns if columns else ['result']
            
        except Exception as e:
            logger.warning(f"No se pudieron extraer nombres de columnas: {e}")
            return ['result']
    
    def get_orders_by_product_id(self, product_id: int) -> List[Dict[str, Any]]:
        """
        Obtiene todas las órdenes para un producto específico
        Usa la query optimizada proporcionada
        """
        query = """
        SELECT 
          p.ID          AS order_id,
          p.post_date   AS order_date,
          p.post_status AS order_status,

          -- Totales / moneda / impuestos / descuentos (cabecera)
          MAX(CASE WHEN pm.meta_key = '_order_currency'      THEN pm.meta_value END) AS order_currency,
          MAX(CASE WHEN pm.meta_key = '_order_total'         THEN pm.meta_value END) AS order_total,
          MAX(CASE WHEN pm.meta_key = '_order_tax'           THEN pm.meta_value END) AS order_tax,
          MAX(CASE WHEN pm.meta_key = '_order_shipping'      THEN pm.meta_value END) AS order_shipping,
          MAX(CASE WHEN pm.meta_key = '_order_shipping_tax'  THEN pm.meta_value END) AS order_shipping_tax,
          MAX(CASE WHEN pm.meta_key = '_cart_discount'       THEN pm.meta_value END) AS cart_discount,
          MAX(CASE WHEN pm.meta_key = '_cart_discount_tax'   THEN pm.meta_value END) AS cart_discount_tax,

          -- Pago
          MAX(CASE WHEN pm.meta_key = '_payment_method'        THEN pm.meta_value END) AS payment_method,
          MAX(CASE WHEN pm.meta_key = '_payment_method_title'  THEN pm.meta_value END) AS payment_method_title,
          MAX(CASE WHEN pm.meta_key = '_transaction_id'        THEN pm.meta_value END) AS transaction_id,
          MAX(CASE WHEN pm.meta_key = '_order_key'             THEN pm.meta_value END) AS order_key,

          -- Fechas / flags operativos
          MAX(CASE WHEN pm.meta_key = '_created_via'                  THEN pm.meta_value END) AS created_via,
          MAX(CASE WHEN pm.meta_key = '_prices_include_tax'           THEN pm.meta_value END) AS prices_include_tax,
          MAX(CASE WHEN pm.meta_key = '_date_paid'                    THEN pm.meta_value END) AS date_paid_ts,
          MAX(CASE WHEN pm.meta_key = '_date_completed'               THEN pm.meta_value END) AS date_completed_ts,
          MAX(CASE WHEN pm.meta_key = '_completed_date'               THEN pm.meta_value END) AS completed_date,
          MAX(CASE WHEN pm.meta_key = '_download_permissions_granted' THEN pm.meta_value END) AS download_permissions_granted,
          MAX(CASE WHEN pm.meta_key = '_order_stock_reduced'          THEN pm.meta_value END) AS order_stock_reduced,
          MAX(CASE WHEN pm.meta_key = '_new_order_email_sent'         THEN pm.meta_value END) AS new_order_email_sent,

          -- Cliente / tracking
          MAX(CASE WHEN pm.meta_key = '_customer_user'         THEN pm.meta_value END) AS customer_user_id,
          MAX(CASE WHEN pm.meta_key = '_customer_ip_address'   THEN pm.meta_value END) AS customer_ip_address,
          MAX(CASE WHEN pm.meta_key = '_customer_user_agent'   THEN pm.meta_value END) AS customer_user_agent,

          -- Facturación
          MAX(CASE WHEN pm.meta_key = '_billing_email'         THEN pm.meta_value END) AS billing_email,
          MAX(CASE WHEN pm.meta_key = '_billing_first_name'    THEN pm.meta_value END) AS billing_first_name,
          MAX(CASE WHEN pm.meta_key = '_billing_last_name'     THEN pm.meta_value END) AS billing_last_name,
          MAX(CASE WHEN pm.meta_key = '_billing_address_1'     THEN pm.meta_value END) AS billing_address_1,
          MAX(CASE WHEN pm.meta_key = '_billing_city'          THEN pm.meta_value END) AS billing_city,
          MAX(CASE WHEN pm.meta_key = '_billing_state'         THEN pm.meta_value END) AS billing_state,
          MAX(CASE WHEN pm.meta_key = '_billing_postcode'      THEN pm.meta_value END) AS billing_postcode,
          MAX(CASE WHEN pm.meta_key = '_billing_country'       THEN pm.meta_value END) AS billing_country,
          MAX(CASE WHEN pm.meta_key = '_billing_phone'         THEN pm.meta_value END) AS billing_phone,

          -- Envío
          MAX(CASE WHEN pm.meta_key = '_shipping_first_name'   THEN pm.meta_value END) AS shipping_first_name,
          MAX(CASE WHEN pm.meta_key = '_shipping_last_name'    THEN pm.meta_value END) AS shipping_last_name,
          MAX(CASE WHEN pm.meta_key = '_shipping_address_1'    THEN pm.meta_value END) AS shipping_address_1,
          MAX(CASE WHEN pm.meta_key = '_shipping_city'         THEN pm.meta_value END) AS shipping_city,
          MAX(CASE WHEN pm.meta_key = '_shipping_state'        THEN pm.meta_value END) AS shipping_state,
          MAX(CASE WHEN pm.meta_key = '_shipping_postcode'     THEN pm.meta_value END) AS shipping_postcode,
          MAX(CASE WHEN pm.meta_key = '_shipping_country'      THEN pm.meta_value END) AS shipping_country,

          -- Productos relacionados
          GROUP_CONCAT(DISTINCT opl.product_id   ORDER BY opl.product_id   SEPARATOR ',') AS product_ids,
          GROUP_CONCAT(DISTINCT opl.variation_id ORDER BY opl.variation_id SEPARATOR ',') AS variation_ids,
          SUM(opl.product_qty) AS total_qty,

          -- Cupones aplicados
          GROUP_CONCAT(DISTINCT oi_coupon.order_item_name ORDER BY oi_coupon.order_item_name SEPARATOR ',') AS coupon_codes,
          SUM(CASE 
              WHEN oim_coupon.meta_key IN ('discount_amount','discount_amount_tax','coupon_amount') 
              THEN CAST(oim_coupon.meta_value AS DECIMAL(20,6)) ELSE 0 END
          ) AS coupons_discount_sum,

          -- Reembolsos y total neto pagado
          COALESCE(r.total_refunded, 0) AS total_refunded,
          (CAST(MAX(CASE WHEN pm.meta_key = '_order_total' THEN pm.meta_value END) AS DECIMAL(20,6)) 
           - COALESCE(r.total_refunded, 0)) AS net_paid

        FROM wp_posts p
        LEFT JOIN wp_postmeta pm 
          ON pm.post_id = p.ID

        -- Lookup de productos
        JOIN wp_wc_order_product_lookup opl 
          ON opl.order_id = p.ID 
         AND (%s IN (opl.product_id, opl.variation_id))

        -- Cupones
        LEFT JOIN wp_woocommerce_order_items oi_coupon
          ON oi_coupon.order_id = p.ID AND oi_coupon.order_item_type = 'coupon'
        LEFT JOIN wp_woocommerce_order_itemmeta oim_coupon
          ON oim_coupon.order_item_id = oi_coupon.order_item_id

        -- Reembolsos
        LEFT JOIN (
          SELECT rp.post_parent AS order_id,
                 SUM(CAST(rpm.meta_value AS DECIMAL(20,6))) AS total_refunded
          FROM wp_posts rp
          JOIN wp_postmeta rpm 
            ON rpm.post_id = rp.ID AND rpm.meta_key = '_refund_amount'
          WHERE rp.post_type = 'shop_order_refund'
          GROUP BY rp.post_parent
        ) r ON r.order_id = p.ID

        WHERE p.post_type = 'shop_order'
          AND p.post_status IN ('wc-completed','wc-processing')  -- ✅ SOLO ÓRDENES PAGADAS
        GROUP BY p.ID
        ORDER BY p.post_date DESC
        """
        
        return self.execute_mysql_query(query, (product_id,))
    
    def get_tickets_by_product_id(self, product_id: int) -> List[Dict[str, Any]]:
        """
        Obtiene todos los tickets para un producto específico usando event_magic_tickets
        Incluye campos personalizados (Custom Attendee Fields) con enfoque híbrido optimizado
        """
        # Paso 1: Obtener tickets básicos con precio (optimizado)
        basic_query = """
        SELECT
          t.ID                       AS ticket_post_id,
          t.post_date                AS ticket_created,
          m_ticket.meta_value        AS ticket_id,
          m_order.meta_value         AS order_id,
          m_prod.meta_value          AS product_id,
          m_var.meta_value           AS variation_id,
          m_att_fn.meta_value        AS attendee_first_name,
          m_att_ln.meta_value        AS attendee_last_name,
          m_att_email.meta_value     AS attendee_email,
          m_price.meta_value         AS price_paid_raw,
          CAST(
            COALESCE(
              FLOOR(
                REPLACE(
                  REPLACE(
                    REPLACE(REGEXP_REPLACE(m_price.meta_value, '<[^>]+>', ''), '&#36;', ''),
                  '.', ''),
                ',', '.')
              ),
              FLOOR(CAST(oim_line_total.meta_value AS DECIMAL(12,4)) / NULLIF(CAST(oim_qty.meta_value AS DECIMAL(12,4)),0))
            )
          AS UNSIGNED) AS price_paid_clean
          
        FROM wp_posts t
        LEFT JOIN wp_postmeta m_prod
          ON m_prod.post_id = t.ID AND m_prod.meta_key = 'WooCommerceEventsProductID'
        LEFT JOIN wp_postmeta m_var
          ON m_var.post_id = t.ID AND m_var.meta_key = 'WooCommerceEventsVariationID'
        LEFT JOIN wp_postmeta m_order
          ON m_order.post_id = t.ID AND m_order.meta_key = 'WooCommerceEventsOrderID'
        LEFT JOIN wp_postmeta m_ticket
          ON m_ticket.post_id = t.ID AND m_ticket.meta_key = 'WooCommerceEventsTicketID'
        LEFT JOIN wp_postmeta m_att_fn
          ON m_att_fn.post_id = t.ID AND m_att_fn.meta_key = 'WooCommerceEventsAttendeeName'
        LEFT JOIN wp_postmeta m_att_ln
          ON m_att_ln.post_id = t.ID AND m_att_ln.meta_key = 'WooCommerceEventsAttendeeLastName'
        LEFT JOIN wp_postmeta m_att_email
          ON m_att_email.post_id = t.ID AND m_att_email.meta_key = 'WooCommerceEventsAttendeeEmail'
        LEFT JOIN wp_postmeta m_price
          ON m_price.post_id = t.ID AND m_price.meta_key = 'WooCommerceEventsPrice'
          
        -- JOIN para obtener precio desde order items (fallback si no está en ticket)
        LEFT JOIN wp_woocommerce_order_items oi
          ON oi.order_id = m_order.meta_value AND oi.order_item_type = 'line_item'
        LEFT JOIN wp_woocommerce_order_itemmeta oim_prod
          ON oim_prod.order_item_id = oi.order_item_id AND oim_prod.meta_key = '_product_id'
        LEFT JOIN wp_woocommerce_order_itemmeta oim_var
          ON oim_var.order_item_id = oi.order_item_id AND oim_var.meta_key = '_variation_id'
        LEFT JOIN wp_woocommerce_order_itemmeta oim_qty
          ON oim_qty.order_item_id = oi.order_item_id AND oim_qty.meta_key = '_qty'
        LEFT JOIN wp_woocommerce_order_itemmeta oim_line_total
          ON oim_line_total.order_item_id = oi.order_item_id AND oim_line_total.meta_key = '_line_total'
          
        WHERE t.post_type = 'event_magic_tickets'
          AND (
            (m_prod.meta_value IS NOT NULL AND CAST(m_prod.meta_value AS UNSIGNED) = %s)
            OR
            (m_var.meta_value  IS NOT NULL AND CAST(m_var.meta_value  AS UNSIGNED) = %s)
          )
          AND (
            oim_var.meta_value IS NULL
            OR CAST(oim_var.meta_value AS UNSIGNED) = CAST(m_var.meta_value AS UNSIGNED)
            OR CAST(oim_prod.meta_value AS UNSIGNED) = CAST(m_prod.meta_value AS UNSIGNED)
          )
        GROUP BY t.ID
        ORDER BY t.ID DESC
        """
        
        tickets = self.execute_mysql_query(basic_query, (product_id, product_id))
        
        if not tickets:
            return tickets
        
        # Paso 2: Obtener definiciones de campos personalizados del evento
        field_labels = self._get_field_labels(product_id)
        
        # Paso 3: Obtener todos los campos personalizados de todos los tickets en una sola query
        ticket_ids = [str(ticket['ticket_post_id']) for ticket in tickets]
        custom_fields_map = self._get_all_custom_fields(ticket_ids, field_labels)
        
        # Paso 4: Combinar datos
        for ticket in tickets:
            ticket_id = ticket['ticket_post_id']
            ticket['custom_attendee_fields'] = custom_fields_map.get(ticket_id)
        
        return tickets
    
    def _get_field_labels(self, product_id: int) -> Dict[str, str]:
        """Obtiene las etiquetas de campos personalizados del evento"""
        try:
            query = """
            SELECT meta_value 
            FROM wp_postmeta 
            WHERE post_id = %s 
              AND meta_key = 'fooevents_custom_attendee_fields_options_serialized'
            """
            
            result = self.execute_mysql_query(query, (product_id,))
            
            if not result or not result[0].get('meta_value'):
                return {}
            
            import json
            fields_config = json.loads(result[0]['meta_value'])
            
            field_labels = {}
            for field_code, field_config in fields_config.items():
                label = field_config.get(f'{field_code}_label', field_code)
                field_labels[field_code] = label
            
            return field_labels
            
        except Exception as e:
            logger.warning(f"Error obteniendo etiquetas de campos: {e}")
            return {}
    
    def _get_all_custom_fields(self, ticket_ids: List[str], field_labels: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        """Obtiene todos los campos personalizados de múltiples tickets en una sola query"""
        if not ticket_ids or not field_labels:
            return {}
        
        try:
            # Crear lista de IDs para la query IN
            ids_placeholder = ','.join(['%s'] * len(ticket_ids))
            
            query = f"""
            SELECT post_id, meta_key, meta_value 
            FROM wp_postmeta 
            WHERE post_id IN ({ids_placeholder})
              AND meta_key LIKE 'fooevents_custom_%%'
              AND meta_key NOT LIKE '%%_label'
              AND meta_key NOT LIKE '%%_type'
              AND meta_key NOT LIKE '%%_options'
              AND meta_key NOT LIKE '%%_def'
              AND meta_key NOT LIKE '%%_req'
              AND meta_key != 'fooevents_custom_attendee_fields_options_serialized'
            """
            
            result = self.execute_mysql_query(query, ticket_ids)
            
            # Organizar por ticket_id
            custom_fields_map = {}
            for row in result:
                ticket_id = row['post_id']
                field_code = row['meta_key'].replace('fooevents_custom_', '')
                field_value = row['meta_value']
                
                if field_value and field_value.strip():
                    if ticket_id not in custom_fields_map:
                        custom_fields_map[ticket_id] = {}
                    
                    # Usar etiqueta legible si está disponible
                    field_label = field_labels.get(field_code, field_code)
                    custom_fields_map[ticket_id][field_label] = field_value
            
            return custom_fields_map
            
        except Exception as e:
            logger.warning(f"Error obteniendo campos personalizados: {e}")
            return {}
    
    
    def get_all_events_with_orders(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los eventos que tienen órdenes asociadas
        """
        query = """
        SELECT DISTINCT
            opl.product_id,
            opl.variation_id,
            COUNT(DISTINCT opl.order_id) as total_orders,
            SUM(opl.product_qty) as total_tickets,
            MIN(p.post_date) as first_order_date,
            MAX(p.post_date) as last_order_date
        FROM wp_wc_order_product_lookup opl
        JOIN wp_posts p ON p.ID = opl.order_id
        WHERE p.post_type = 'shop_order'
          AND p.post_status IN ('wc-completed','wc-processing','wc-on-hold','wc-pending')
        GROUP BY opl.product_id, opl.variation_id
        ORDER BY total_orders DESC
        """
        
        return self.execute_mysql_query(query)
    
    def get_product_info(self, product_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene información básica de un producto/evento
        """
        query = """
        SELECT 
            p.ID as product_id,
            p.post_title as product_name,
            p.post_content as product_description,
            p.post_status as product_status,
            p.post_date as created_date,
            p.post_modified as modified_date
        FROM wp_posts p
        WHERE p.ID = %s AND p.post_type IN ('product', 'product_variation')
        """
        
        results = self.execute_mysql_query(query, (product_id,))
        return results[0] if results else None
    
    def test_connection(self) -> bool:
        """
        Prueba la conexión MySQL ejecutando una query simple
        """
        try:
            result = self.execute_mysql_query("SELECT 1 as test")
            return len(result) > 0 and result[0].get('test') == '1'
        except Exception as e:
            logger.error(f"Error probando conexión MySQL: {e}")
            return False
    
    def __enter__(self):
        """Context manager entry - establece conexión automáticamente"""
        logger.info("Iniciando context manager SSH/MySQL")
        if not self._ensure_connection():
            raise SSHMySQLError("No se pudo establecer conexión SSH")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cierra conexión automáticamente"""
        logger.info("Cerrando context manager SSH/MySQL")
        self.disconnect()
        
        # No suprimir excepciones
        return False

# Context manager para uso fácil
@contextmanager
def ssh_mysql_connection():
    """
    Context manager para manejo automático de conexión MySQL vía SSH
    
    Usage:
        with ssh_mysql_connection() as db:
            orders = db.get_orders_by_product_id(12345)
    """
    handler = SSHMySQLHandler()
    try:
        yield handler.__enter__()
    finally:
        handler.__exit__(None, None, None)
