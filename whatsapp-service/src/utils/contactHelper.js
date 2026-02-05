/**
 * Utility functions for handling WhatsApp contacts
 */

/**
 * Format phone number for display
 * @param {string} number - Phone number (e.g., "56947884342")
 * @returns {string} Formatted phone number (e.g., "+56 9 4788 4342")
 */
function formatPhoneNumber(number) {
    if (!number || typeof number !== 'string') {
        return number || '';
    }
    
    // Remove all non-digit characters
    const digitsOnly = number.replace(/\D/g, '');
    
    if (!digitsOnly) {
        return number;
    }
    
    // Format Chilean numbers (country code 56)
    if (digitsOnly.startsWith('56') && digitsOnly.length === 11) {
        // Format: +56 9 4788 4342
        return `+${digitsOnly.slice(0, 2)} ${digitsOnly.slice(2, 3)} ${digitsOnly.slice(3, 7)} ${digitsOnly.slice(7)}`;
    }
    
    // Format Brazilian numbers (country code 55)
    if (digitsOnly.startsWith('55') && digitsOnly.length === 12 || digitsOnly.length === 13) {
        // Format: +55 11 98765 4321
        if (digitsOnly.length === 12) {
            return `+${digitsOnly.slice(0, 2)} ${digitsOnly.slice(2, 4)} ${digitsOnly.slice(4, 9)} ${digitsOnly.slice(9)}`;
        } else {
            return `+${digitsOnly.slice(0, 2)} ${digitsOnly.slice(2, 4)} ${digitsOnly.slice(4, 10)} ${digitsOnly.slice(10)}`;
        }
    }
    
    // Default format: add + if missing
    if (!digitsOnly.startsWith('+')) {
        return `+${digitsOnly}`;
    }
    
    return digitsOnly;
}

/**
 * Extract phone number from chat ID
 * @param {string} chatId - Chat ID (e.g., "56947884342@c.us", "222462226747521@lid", "120363404401101559@g.us")
 * @returns {string|null} Phone number or null if not a valid individual chat ID
 */
function extractPhoneFromId(chatId) {
    if (!chatId || typeof chatId !== 'string') {
        return null;
    }
    // Individual chats: @c.us (standard) or @lid (linked device)
    if (chatId.endsWith('@c.us')) {
        const phone = chatId.replace('@c.us', '');
        return /^\d+$/.test(phone) ? phone : null;
    }
    if (chatId.endsWith('@lid')) {
        const part = chatId.replace('@lid', '');
        return /^\d+$/.test(part) ? part : null;
    }
    return null;
}

/**
 * Check if contactId uses @lid format (linked device - not supported by getContactById)
 * @param {string} contactId - Contact ID
 * @returns {boolean}
 */
function isLidContact(contactId) {
    return contactId && typeof contactId === 'string' && contactId.endsWith('@lid');
}

/**
 * Return basic contact info from ID without calling getContactById (for @lid or fallback)
 * @param {string} contactId - Contact ID
 * @returns {object} Basic contact info
 */
function getBasicContactInfoFromId(contactId) {
    const safe = contactId != null ? String(contactId) : '';
    const number = extractPhoneFromId(safe);
    return {
        id: safe,
        number: number,
        formattedNumber: number ? formatPhoneNumber(number) : null,
        name: null,
        pushname: null,
        profilePictureUrl: null
    };
}

/** Timeout for getContactById (ms) - prevents ProtocolError hang */
const GET_CONTACT_TIMEOUT_MS = 8000;

/**
 * Normalize contact ID from string or object (handles { user, server }, { _serialized }, etc.)
 * @param {string|object} contactId
 * @returns {string}
 */
function normalizeContactId(contactId) {
    if (!contactId) return '';
    if (typeof contactId === 'string') return contactId;
    const serialized = contactId?._serialized ?? contactId?.id?._serialized;
    if (serialized && typeof serialized === 'string') return serialized;
    const user = contactId?.id?.user ?? contactId?.user;
    const server = contactId?.id?.server ?? contactId?.server ?? 'c.us';
    if (user) return `${user}@${server}`;
    return '';
}

/**
 * Get contact information from contact ID (enterprise: timeout, ProtocolError fallback)
 * @param {object} client - WhatsApp client instance
 * @param {string|object} contactId - Contact ID (e.g., "56947884342@c.us" or { user, server })
 * @returns {Promise<object>} Contact info with name, number, pushname, profilePictureUrl
 */
async function getContactInfo(client, contactId) {
    const idStr = normalizeContactId(contactId);
    // NUNCA llamar getContactById para @lid - la librería lanza _serialized undefined
    if (!idStr || idStr.includes('@lid') || idStr.includes('[object Object]')) {
        return getBasicContactInfoFromId(idStr || '');
    }
    try {
        const contactPromise = client.getContactById(idStr);
        const timeoutPromise = new Promise((_, reject) =>
            setTimeout(() => reject(new Error('getContactById timeout')), GET_CONTACT_TIMEOUT_MS)
        );
        const contact = await Promise.race([contactPromise, timeoutPromise]);
        if (!contact || !contact.id) {
            return getBasicContactInfoFromId(idStr);
        }
        const number = contact.number || extractPhoneFromId(idStr) || null;
        const formattedNumber = number ? formatPhoneNumber(number) : null;
        let profilePictureUrl = null;
        try {
            profilePictureUrl = await contact.getProfilePicUrl() || null;
        } catch (_) {
            profilePictureUrl = null;
        }
        return {
            id: contact.id?._serialized || idStr,
            number: number,
            formattedNumber: formattedNumber,
            name: contact.name || null,
            pushname: contact.pushname || null,
            profilePictureUrl: profilePictureUrl
        };
    } catch (_error) {
        return getBasicContactInfoFromId(idStr);
    }
}

/**
 * Extract phone number from contact object
 * @param {object} contact - Contact object from whatsapp-web.js
 * @returns {string|null} Phone number
 */
function getContactNumber(contact) {
    if (!contact) {
        return null;
    }
    
    // Try different properties
    if (contact.number) {
        return contact.number;
    }
    
    if (contact.id && contact.id.user) {
        return contact.id.user;
    }
    
    if (contact.id && typeof contact.id._serialized === 'string') {
        return extractPhoneFromId(contact.id._serialized);
    }
    
    return null;
}

/**
 * Get display name for a contact
 * @param {object} contact - Contact object
 * @returns {string} Display name (pushname > name > number > 'Unknown')
 */
function getContactDisplayName(contact) {
    if (!contact) {
        return 'Unknown';
    }
    
    // Prefer pushname (WhatsApp name), then name, then number
    if (contact.pushname) {
        return contact.pushname;
    }
    
    if (contact.name) {
        return contact.name;
    }
    
    const number = getContactNumber(contact);
    if (number) {
        return formatPhoneNumber(number);
    }
    
    return 'Unknown';
}

module.exports = {
    formatPhoneNumber,
    extractPhoneFromId,
    getContactInfo,
    getContactNumber,
    getContactDisplayName,
    isLidContact,
    getBasicContactInfoFromId,
    normalizeContactId
};

