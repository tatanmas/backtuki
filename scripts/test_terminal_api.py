#!/usr/bin/env python
"""
Script de testing para API del Terminal.
Ejecutar: python manage.py shell < scripts/test_terminal_api.py
O: docker exec backtuki-backend-1 python manage.py shell < scripts/test_terminal_api.py
"""

from apps.terminal.models import TerminalTrip, TerminalCompany, TerminalRoute, TerminalExcelUpload

print("=" * 60)
print("TESTING TERMINAL API - Estado Actual")
print("=" * 60)

# Estadísticas generales
print("\n📊 ESTADÍSTICAS GENERALES:")
print(f"  - Empresas: {TerminalCompany.objects.count()}")
print(f"  - Rutas: {TerminalRoute.objects.count()}")
print(f"  - Viajes totales: {TerminalTrip.objects.count()}")
print(f"  - Viajes activos: {TerminalTrip.objects.filter(is_active=True).count()}")
print(f"  - Viajes agotados: {TerminalTrip.objects.filter(status='sold_out').count()}")
print(f"  - Salidas: {TerminalTrip.objects.filter(trip_type='departure').count()}")
print(f"  - Llegadas: {TerminalTrip.objects.filter(trip_type='arrival').count()}")
print(f"  - Uploads procesados: {TerminalExcelUpload.objects.count()}")

# Empresas
print("\n🏢 EMPRESAS:")
for company in TerminalCompany.objects.all()[:10]:
    print(f"  - {company.name} (ID: {company.id})")
    print(f"    Booking Method: {company.booking_method}")
    if company.booking_url:
        print(f"    URL: {company.booking_url}")
    if company.booking_phone:
        print(f"    Teléfono: {company.booking_phone}")
    if company.booking_whatsapp:
        print(f"    WhatsApp: {company.booking_whatsapp}")

# Rutas más usadas
print("\n🛣️  RUTAS (Top 10):")
for route in TerminalRoute.objects.all()[:10]:
    count = TerminalTrip.objects.filter(route=route).count()
    print(f"  - {route.origin} → {route.destination} ({count} viajes)")

# Viajes recientes
print("\n🚌 VIAJES RECIENTES (Últimos 10):")
for trip in TerminalTrip.objects.select_related('company', 'route').order_by('-created_at')[:10]:
    time_str = trip.departure_time.strftime('%H:%M') if trip.departure_time else (
        trip.arrival_time.strftime('%H:%M') if trip.arrival_time else 'N/A'
    )
    print(f"  - {trip.date} {time_str} | {trip.company.name} | {trip.route.origin} → {trip.route.destination}")
    print(f"    Tipo: {trip.trip_type} | Estado: {trip.status} | Activo: {trip.is_active}")

# Uploads recientes
print("\n📤 UPLOADS RECIENTES:")
for upload in TerminalExcelUpload.objects.order_by('-created_at')[:5]:
    print(f"  - {upload.file_name} ({upload.upload_type})")
    print(f"    Estado: {upload.status}")
    print(f"    Creados: {upload.trips_created} | Actualizados: {upload.trips_updated}")
    if upload.errors:
        print(f"    Errores: {len(upload.errors)}")

# Verificar problemas comunes
print("\n⚠️  VERIFICACIONES:")
issues = []

# Viajes sin hora
trips_no_time = TerminalTrip.objects.filter(
    departure_time__isnull=True,
    arrival_time__isnull=True
).count()
if trips_no_time > 0:
    issues.append(f"  - {trips_no_time} viajes sin hora de salida ni llegada")

# Viajes con ambos tiempos (puede ser válido pero inusual)
trips_both_times = TerminalTrip.objects.filter(
    departure_time__isnull=False,
    arrival_time__isnull=False
).count()
print(f"  - {trips_both_times} viajes con ambos tiempos (puede ser válido)")

# Viajes activos pero agotados (deberían estar inactivos)
trips_active_soldout = TerminalTrip.objects.filter(
    is_active=True,
    status='sold_out'
).count()
if trips_active_soldout > 0:
    issues.append(f"  - {trips_active_soldout} viajes activos pero agotados (deberían estar inactivos)")

if issues:
    print("\n⚠️  PROBLEMAS ENCONTRADOS:")
    for issue in issues:
        print(issue)
else:
    print("\n✅ No se encontraron problemas")

print("\n" + "=" * 60)
print("Para más detalles, usar Django shell:")
print("  python manage.py shell")
print("  >>> from apps.terminal.models import TerminalTrip")
print("  >>> TerminalTrip.objects.all()")
print("=" * 60)

