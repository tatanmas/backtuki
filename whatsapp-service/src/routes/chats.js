// Chats routes
const express = require('express');
const router = express.Router();
const config = require('../config');
const chatHelper = require('../utils/chatHelper');
const contactHelper = require('../utils/contactHelper');

/**
 * GET /api/chats
 * Get all WhatsApp chats
 */
router.get('/api/chats', async (req, res) => {
    if (!config.isReady) return res.status(503).json({ error: 'WhatsApp no listo' });
    
    try {
        const chats = await config.client.getChats();
        const chatsData = await Promise.all(chats.map(async (chat) => {
            try {
                const isGroup = chat.isGroup;
                
                // Obtener información básica
                let unreadCount = 0;
                try {
                    if (typeof chat.getUnreadCount === 'function') {
                        unreadCount = await chat.getUnreadCount();
                    }
                } catch (e) {
                    // getUnreadCount puede fallar, usar 0 como fallback
                    unreadCount = 0;
                }
                
                let messages = [];
                try {
                    if (typeof chat.fetchMessages === 'function') {
                        messages = await chat.fetchMessages({ limit: 1 });
                    }
                } catch (e) {
                    // fetchMessages puede fallar
                    messages = [];
                }
                
                let chatInfo = {
                    chat_id: chat.id._serialized,
                    type: isGroup ? 'group' : 'individual',
                    unread_count: unreadCount,
                    last_message: messages[0] ? {
                        text: messages[0].body,
                        timestamp: messages[0].timestamp
                    } : null
                };
                
                if (isGroup) {
                    // Para grupos, obtener información adicional
                    chatInfo.name = chatHelper.getChatDisplayName(chat);
                    chatInfo.description = chat.description || null;
                    
                    // Obtener foto de perfil del grupo
                    chatInfo.profile_picture_url = await chatHelper.getProfilePicture(chat);
                    
                    // Obtener participantes usando helper
                    try {
                        const participants = await chatHelper.getGroupParticipants(config.client, chat);
                        chatInfo.participants = participants.map(p => ({
                            id: p.id,
                            phone: p.phone,
                            formattedPhone: p.formattedPhone,
                            name: p.name,
                            pushname: p.pushname,
                            displayName: p.displayName,
                            isAdmin: p.isAdmin,
                            profile_picture_url: p.profilePictureUrl
                        }));
                    } catch (e) {
                        console.error(`Error getting participants for group ${chat.id._serialized}:`, e);
                        chatInfo.participants = [];
                    }
                } else {
                    // Para chats individuales, obtener información del contacto
                    const phoneFromId = contactHelper.extractPhoneFromId(chat.id._serialized);
                    const isLid = contactHelper.isLidContact(chat.id._serialized);
                    // @lid: getContact()/getContactById fallan - usar solo datos del ID
                    if (isLid) {
                        if (phoneFromId) {
                            chatInfo.name = contactHelper.formatPhoneNumber(phoneFromId);
                            chatInfo.phone = chatInfo.name;
                        } else {
                            chatInfo.name = chat.name || 'Unknown';
                            chatInfo.phone = null;
                        }
                        chatInfo.whatsapp_name = null;
                        chatInfo.profile_picture_url = null;
                    } else {
                    try {
                        const contact = await chat.getContact();
                        
                        // Obtener número de teléfono (preferir del contacto, fallback al chat_id)
                        let phone = contactHelper.getContactNumber(contact);
                        if (!phone && phoneFromId) {
                            phone = phoneFromId;
                        }
                        
                        // Formatear número de teléfono
                        if (phone) {
                            chatInfo.phone = contactHelper.formatPhoneNumber(phone);
                            // El nombre por defecto será el número formateado
                            const formattedPhone = chatInfo.phone;
                            
                            // Obtener nombre usando helper
                            const displayName = chatHelper.getChatDisplayName(chat, contact);
                            chatInfo.name = (displayName && displayName !== 'Unknown') ? displayName : formattedPhone;
                            chatInfo.whatsapp_name = chatHelper.getWhatsAppName(contact);
                            
                            // Si no hay whatsapp_name, usar el nombre del chat si existe
                            if (!chatInfo.whatsapp_name && chat.name && chat.name !== formattedPhone) {
                                chatInfo.whatsapp_name = chat.name;
                            }
                        } else {
                            // Si no hay número, usar el nombre del chat o 'Unknown'
                            chatInfo.name = chat.name || 'Unknown';
                            chatInfo.whatsapp_name = null;
                            chatInfo.phone = null;
                        }
                        
                        // Intentar obtener foto de perfil
                        chatInfo.profile_picture_url = await chatHelper.getProfilePicture(contact);
                    } catch (e) {
                        if (phoneFromId) {
                            chatInfo.name = contactHelper.formatPhoneNumber(phoneFromId);
                            chatInfo.phone = chatInfo.name;
                        } else {
                            chatInfo.name = chat.name || 'Unknown';
                            chatInfo.phone = null;
                        }
                        chatInfo.whatsapp_name = null;
                        chatInfo.profile_picture_url = null;
                    }
                    }
                }
                
                return chatInfo;
            } catch (error) {
                console.error(`Error processing chat ${chat.id._serialized}:`, error);
                // Fallback básico
                const isGroup = chat.isGroup;
                const phone = !isGroup ? contactHelper.extractPhoneFromId(chat.id._serialized) : null;
                return {
                    chat_id: chat.id._serialized,
                    name: isGroup ? 'Unknown Group' : (phone ? contactHelper.formatPhoneNumber(phone) : 'Unknown'),
                    type: isGroup ? 'group' : 'individual',
                    phone: phone ? contactHelper.formatPhoneNumber(phone) : null,
                    unread_count: 0,
                    last_message: null
                };
            }
        }));
        
        res.json({ chats: chatsData });
    } catch (error) {
        console.error('Error getting chats:', error);
        res.status(500).json({ error: 'Error getting chats' });
    }
});

/**
 * GET /api/chats/:chatId/messages
 * Get message history for a specific chat
 */
router.get('/api/chats/:chatId/messages', async (req, res) => {
    if (!config.isReady) return res.status(503).json({ error: 'WhatsApp no listo' });
    
    try {
        const chatId = req.params.chatId;
        const limit = parseInt(req.query.limit) || 1000; // Por defecto 1000 mensajes
        
        console.log(`[API /api/chats/${chatId}/messages] Fetching messages (limit: ${limit})`);
        
        const chat = await config.client.getChatById(chatId);
        
        if (!chat) {
            return res.status(404).json({ error: 'Chat not found' });
        }
        
        // Cargar mensajes del historial
        const messages = await chat.fetchMessages({ limit: limit });
        
        console.log(`[API /api/chats/${chatId}/messages] Found ${messages.length} messages`);
        
        // Procesar mensajes para incluir información completa
        const contactHelper = require('../utils/contactHelper');
        const messagesData = await Promise.all(messages.map(async (message) => {
            try {
                const isFromMe = message.fromMe;
                const isGroup = chat.isGroup;
                
                let senderName = null;
                let senderPhone = null;
                
                // Para grupos, obtener información del remitente (evitar getContactInfo para @lid)
                if (isGroup && !isFromMe && message.author) {
                    const authorStr = contactHelper.normalizeContactId ? contactHelper.normalizeContactId(message.author) : (typeof message.author === 'string' ? message.author : (message.author?._serialized || ''));
                    if (contactHelper.isLidContact(authorStr) || (authorStr && authorStr.includes('@lid'))) {
                        const basic = contactHelper.getBasicContactInfoFromId(authorStr);
                        senderName = basic.formattedNumber || null;
                        senderPhone = basic.number || (authorStr ? authorStr.replace(/@\w+\.?\w*/g, '') : null);
                    } else {
                        try {
                            const senderContactInfo = await contactHelper.getContactInfo(config.client, authorStr);
                            senderName = senderContactInfo.pushname || senderContactInfo.name || null;
                            senderPhone = senderContactInfo.number || null;
                        } catch (e) {
                            senderPhone = authorStr.replace('@c.us', '').replace('@g.us', '').replace('@lid', '');
                        }
                    }
                }

                const mediaType = message.type || 'chat';
                const MEDIA_PLACEHOLDERS = { ptt: '[Audio de voz]', audio: '[Audio]', image: '[Imagen]', video: '[Video]', document: '[Documento]', sticker: '[Sticker]' };
                let content = message.body || '';
                if (!content && MEDIA_PLACEHOLDERS[mediaType]) content = MEDIA_PLACEHOLDERS[mediaType];
                else if (!content && mediaType !== 'chat') content = `[${mediaType}]`;

                let replyToWhatsappId = null;
                try {
                    if (message.hasQuotedMsg && typeof message.getQuotedMessage === 'function') {
                        const quoted = await message.getQuotedMessage();
                        if (quoted && quoted.id) replyToWhatsappId = quoted.id._serialized || quoted.id.id || null;
                    }
                } catch (_) {}

                return {
                    id: message.id._serialized,
                    whatsapp_id: message.id._serialized,
                    phone: isFromMe ? (message.to.replace('@c.us', '').replace('@g.us', '')) : (message.from.replace('@c.us', '').replace('@g.us', '')),
                    chat_id: chatId,
                    chat_type: isGroup ? 'group' : 'individual',
                    type: isFromMe ? 'out' : 'in',
                    content,
                    timestamp: message.timestamp,
                    from_me: isFromMe,
                    sender_name: senderName,
                    sender_phone: senderPhone,
                    media_type: mediaType,
                    reply_to_whatsapp_id: replyToWhatsappId,
                };
            } catch (e) {
                console.error(`Error processing message ${message.id._serialized}:`, e);
                return null;
            }
        }));
        
        // Filtrar mensajes nulos (errores)
        const validMessages = messagesData.filter(m => m !== null);
        
        res.json({
            chat_id: chatId,
            messages: validMessages,
            total: validMessages.length
        });
    } catch (error) {
        console.error(`Error getting messages for chat ${req.params.chatId}:`, error);
        res.status(500).json({ error: 'Error getting messages', details: error.message });
    }
});

module.exports = router;
