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
 * @param {string} chatId - Chat ID (e.g., "56947884342@c.us" or "120363404401101559@g.us")
 * @returns {string|null} Phone number or null if not a valid individual chat ID
 */
function extractPhoneFromId(chatId) {
    if (!chatId || typeof chatId !== 'string') {
        return null;
    }
    
    // Only extract from individual chats (@c.us)
    if (!chatId.endsWith('@c.us')) {
        return null;
    }
    
    // Extract number part
    const phone = chatId.replace('@c.us', '');
    
    // Validate it's a number
    if (/^\d+$/.test(phone)) {
        return phone;
    }
    
    return null;
}

/**
 * Get contact information from contact ID
 * @param {object} client - WhatsApp client instance
 * @param {string} contactId - Contact ID (e.g., "56947884342@c.us")
 * @returns {Promise<object>} Contact info with name, number, pushname, profilePictureUrl
 */
async function getContactInfo(client, contactId) {
    try {
        const contact = await client.getContactById(contactId);
        
        const number = contact.number || extractPhoneFromId(contactId) || null;
        const formattedNumber = number ? formatPhoneNumber(number) : null;
        
        let profilePictureUrl = null;
        try {
            profilePictureUrl = await contact.getProfilePicUrl() || null;
        } catch (e) {
            // Profile picture not available or permission denied
            profilePictureUrl = null;
        }
        
        return {
            id: contact.id._serialized,
            number: number,
            formattedNumber: formattedNumber,
            name: contact.name || null,
            pushname: contact.pushname || null,
            profilePictureUrl: profilePictureUrl
        };
    } catch (error) {
        console.error(`Error getting contact info for ${contactId}:`, error);
        // Return basic info from ID
        const number = extractPhoneFromId(contactId);
        return {
            id: contactId,
            number: number,
            formattedNumber: number ? formatPhoneNumber(number) : null,
            name: null,
            pushname: null,
            profilePictureUrl: null
        };
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
    getContactDisplayName
};

