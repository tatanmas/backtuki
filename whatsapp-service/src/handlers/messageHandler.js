// Message handler
const config = require('../config');
const contactHelper = require('../utils/contactHelper');
const chatHelper = require('../utils/chatHelper');
const { createLogger } = require('../utils/logger');

const logger = createLogger('MessageHandler');

/**
 * Handle incoming WhatsApp messages
 */
async function handleMessage(message, client) {
    // IMPORTANTE: Capturar TODOS los mensajes, incluyendo los propios (fromMe)
    // Esto permite tener el flujo completo del chat
    
    const isFromMe = message.fromMe;
    
    // Para mensajes propios, usar message.to; para entrantes, usar message.from
    const chatId = isFromMe ? message.to : message.from;
    const isGroup = chatId.endsWith('@g.us');
    const chatType = isGroup ? 'group' : 'individual';
    
    // Obtener información del chat
    let chatName = null;
    let whatsappName = null;
    let profilePictureUrl = null;
    let senderName = null;
    let senderPhone = null;
    let phoneNumber = null;
    
    try {
        const chat = await message.getChat();
        
        if (isGroup) {
            // Para grupos, obtener nombre del grupo
            chatName = chatHelper.getChatDisplayName(chat);
            
            // Para mensajes de grupo, obtener información del remitente (si no es propio)
            if (isGroup && !isFromMe && message.author) {
                logger.debug('Group message received, extracting sender info', { author: message.author });
                try {
                    const senderContactInfo = await contactHelper.getContactInfo(client, message.author);
                    senderName = senderContactInfo.pushname || senderContactInfo.name || null;
                    senderPhone = senderContactInfo.number || null;
                    logger.debug('Sender info extracted', { senderName, senderPhone });
                } catch (e) {
                    logger.warn('Failed to get sender info, using fallback', { author: message.author, error: e.message });
                    senderPhone = message.author.replace('@c.us', '').replace('@g.us', '');
                }
            } else if (isGroup && isFromMe) {
                logger.debug('Own message in group, skipping sender extraction');
            } else if (isGroup && !message.author) {
                logger.warn('Group message without author field', {
                    chatId: chatId,
                    messageId: message.id._serialized,
                    fromMe: isFromMe
                });
            }
            
            // Obtener foto de perfil del grupo
            profilePictureUrl = await chatHelper.getProfilePicture(chat);
            
            // Para grupos, phoneNumber es el ID del grupo (no hay número individual)
            phoneNumber = chatId.replace('@g.us', '');
        } else {
            // Para chats individuales
            let contact = null;
            
            if (isFromMe) {
                // Para mensajes propios, obtener el contacto del destinatario
                try {
                    contact = await chat.getContact();
                } catch (e) {
                    logger.warn('Failed to get contact for own message', { error: e.message });
                }
            } else {
                // Para mensajes entrantes, obtener el contacto del remitente
                try {
                    contact = await message.getContact();
                } catch (e) {
                    logger.warn('Failed to get contact for incoming message', { error: e.message });
                }
            }
            
            // Obtener nombre y número usando helpers
            if (contact) {
                chatName = chatHelper.getChatDisplayName(chat, contact);
                whatsappName = chatHelper.getWhatsAppName(contact);
                phoneNumber = contactHelper.getContactNumber(contact);
                profilePictureUrl = await chatHelper.getProfilePicture(contact);
            } else {
                // Fallback: extraer del chat ID
                phoneNumber = contactHelper.extractPhoneFromId(chatId);
                chatName = phoneNumber ? contactHelper.formatPhoneNumber(phoneNumber) : chatId.replace('@c.us', '');
            }
        }
    } catch (e) {
        logger.error('Failed to get chat info', { chatId, error: e.message });
        // Fallback: extraer número del chat ID
        if (!isGroup) {
            phoneNumber = contactHelper.extractPhoneFromId(chatId);
            chatName = phoneNumber ? contactHelper.formatPhoneNumber(phoneNumber) : chatId.replace('@c.us', '').replace('@g.us', '');
        } else {
            chatName = chatId.replace('@g.us', '');
        }
    }
    
    // Asegurar que phoneNumber esté formateado correctamente (para no grupos)
    if (phoneNumber && !isGroup) {
        // phoneNumber ya debería estar en formato correcto si viene de contactHelper
        // pero por seguridad, si es solo dígitos, lo formateamos
        if (/^\d+$/.test(phoneNumber)) {
            phoneNumber = contactHelper.formatPhoneNumber(phoneNumber);
        }
    }
    
    // Enviar a Django webhook
    try {
        const timestamp = message.timestamp;
        
        const payload = {
            id: message.id.id,
            phone: phoneNumber || chatId.replace('@c.us', '').replace('@g.us', ''),
            chat_id: chatId,
            chat_type: chatType,
            chat_name: chatName,
            whatsapp_name: whatsappName,
            profile_picture_url: profilePictureUrl,
            text: message.body,
            timestamp: timestamp,
            from_me: isFromMe,
            sender_name: senderName || null,
            sender_phone: senderPhone || null
        };
        
        // Log message reception
        logger.info('Message received', {
            type: isFromMe ? 'outgoing' : 'incoming',
            chatType: chatType,
            chatName: chatName,
            textPreview: message.body ? message.body.substring(0, 50) : null
        });
        
        const response = await fetch(`${config.DJANGO_API_URL}/api/v1/whatsapp/webhook/process-message/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            logger.debug('Message sent to Django successfully');
        } else {
            logger.warn('Django webhook returned non-OK status', { status: response.status });
        }
    } catch (error) {
        logger.error('Failed to send message to Django', { error: error.message });
    }
}

module.exports = {
    handleMessage
};
