/**
 * Utility functions for handling WhatsApp chats
 */
const contactHelper = require('./contactHelper');

/**
 * Get display name for a chat
 * @param {object} chat - Chat object from whatsapp-web.js
 * @param {object} contact - Contact object (for individual chats)
 * @returns {string} Display name
 */
function getChatDisplayName(chat, contact = null) {
    if (!chat) {
        return 'Unknown';
    }
    
    // For groups, use chat.name
    if (chat.isGroup) {
        return chat.name || 'Unknown Group';
    }
    
    // For individual chats, prefer contact info
    if (contact) {
        return contactHelper.getContactDisplayName(contact);
    }
    
    // Fallback to chat.name or number
    if (chat.name) {
        return chat.name;
    }
    
    // Try to extract number from chat ID
    const number = contactHelper.extractPhoneFromId(chat.id._serialized);
    if (number) {
        return contactHelper.formatPhoneNumber(number);
    }
    
    return 'Unknown';
}

/**
 * Get phone number for an individual chat
 * @param {object} chat - Chat object
 * @param {object} contact - Contact object
 * @returns {string|null} Phone number (formatted)
 */
function getChatPhoneNumber(chat, contact = null) {
    if (!chat || chat.isGroup) {
        return null;
    }
    
    // Try contact first
    if (contact) {
        const number = contactHelper.getContactNumber(contact);
        if (number) {
            return contactHelper.formatPhoneNumber(number);
        }
    }
    
    // Try chat ID
    const number = contactHelper.extractPhoneFromId(chat.id._serialized);
    if (number) {
        return contactHelper.formatPhoneNumber(number);
    }
    
    return null;
}

/**
 * Get group participants with complete information
 * @param {object} client - WhatsApp client instance
 * @param {object} groupChat - Group chat object
 * @returns {Promise<array>} Array of participant objects
 */
async function getGroupParticipants(client, groupChat) {
    try {
        const participants = await groupChat.participants;
        
        if (!participants || !Array.isArray(participants)) {
            return [];
        }
        
        // Map participants to get complete info
        const participantsData = await Promise.all(
            participants.map(async (p) => {
                try {
                    // Get contact info for each participant
                    const contactInfo = await contactHelper.getContactInfo(client, p.id._serialized);
                    
                    return {
                        id: p.id._serialized,
                        phone: contactInfo.number || p.id.user || null,
                        formattedPhone: contactInfo.formattedNumber,
                        name: contactInfo.name || p.name || null,
                        pushname: contactInfo.pushname || p.pushname || null,
                        displayName: contactInfo.pushname || contactInfo.name || contactInfo.formattedNumber || 'Unknown',
                        isAdmin: p.isAdmin || false,
                        profilePictureUrl: contactInfo.profilePictureUrl
                    };
                } catch (error) {
                    console.error(`Error getting participant info for ${p.id._serialized}:`, error);
                    // Return basic info if we can't get full contact info
                    const number = p.id.user || contactHelper.extractPhoneFromId(p.id._serialized);
                    return {
                        id: p.id._serialized,
                        phone: number,
                        formattedPhone: number ? contactHelper.formatPhoneNumber(number) : null,
                        name: p.name || null,
                        pushname: p.pushname || null,
                        displayName: p.pushname || p.name || (number ? contactHelper.formatPhoneNumber(number) : 'Unknown'),
                        isAdmin: p.isAdmin || false,
                        profilePictureUrl: null
                    };
                }
            })
        );
        
        return participantsData;
    } catch (error) {
        console.error(`Error getting group participants:`, error);
        return [];
    }
}

/**
 * Get profile picture URL with error handling
 * @param {object} contactOrChat - Contact or Chat object
 * @returns {Promise<string|null>} Profile picture URL or null
 */
async function getProfilePicture(contactOrChat) {
    if (!contactOrChat) {
        return null;
    }
    
    // Retry logic: intentar hasta 2 veces
    let lastError = null;
    for (let attempt = 1; attempt <= 2; attempt++) {
        try {
            const url = await contactOrChat.getProfilePicUrl();
            if (url) {
                return url;
            }
            // Si retorna null, no hay foto disponible (no es un error)
            return null;
        } catch (error) {
            lastError = error;
            // Si es un error de permisos o no disponible, no reintentar
            if (error.message && (
                error.message.includes('permission') || 
                error.message.includes('not available') ||
                error.message.includes('404') ||
                error.message.includes('403')
            )) {
                return null;
            }
            // Para otros errores, esperar un poco antes de reintentar
            if (attempt < 2) {
                await new Promise(resolve => setTimeout(resolve, 500));
            }
        }
    }
    
    // Si llegamos aquí, todos los intentos fallaron
    // No es crítico, solo loguear warning
    return null;
}

/**
 * Get WhatsApp name for a contact
 * @param {object} contact - Contact object
 * @returns {string|null} WhatsApp name (pushname)
 */
function getWhatsAppName(contact) {
    if (!contact) {
        return null;
    }
    
    return contact.pushname || contact.name || null;
}

module.exports = {
    getChatDisplayName,
    getChatPhoneNumber,
    getGroupParticipants,
    getProfilePicture,
    getWhatsAppName
};

