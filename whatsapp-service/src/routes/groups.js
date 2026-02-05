// Groups routes
const express = require('express');
const router = express.Router();
const config = require('../config');
const chatHelper = require('../utils/chatHelper');

/**
 * GET /api/groups
 * Get all WhatsApp groups
 */
router.get('/api/groups', async (req, res) => {
    console.log('[API /api/groups] Request received');
    console.log('[API /api/groups] isReady:', config.isReady);
    
    if (!config.isReady) {
        console.log('[API /api/groups] WhatsApp not ready, returning 503');
        return res.status(503).json({ error: 'WhatsApp no listo' });
    }
    
    try {
        console.log('[API /api/groups] Fetching chats from client...');
        const chats = await config.client.getChats();
        console.log('[API /api/groups] Total chats retrieved:', chats.length);
        
        // Filtrar solo grupos y procesarlos
        const groupsData = [];
        for (const chat of chats) {
            if (!chat.isGroup) continue;
            
            console.log(`[API /api/groups] Processing group: ${chat.id._serialized}`);
            try {
                // Obtener información básica
                let unreadCount = 0;
                try {
                    if (typeof chat.getUnreadCount === 'function') {
                        unreadCount = await chat.getUnreadCount();
                    }
                } catch (e) {
                    console.warn(`Could not get unread count for group ${chat.id._serialized}:`, e.message);
                }
                
                let messages = [];
                try {
                    messages = await chat.fetchMessages({ limit: 1 });
                } catch (e) {
                    console.warn(`Could not fetch messages for group ${chat.id._serialized}:`, e.message);
                }
                
                const groupInfo = {
                    chat_id: chat.id._serialized,
                    name: chatHelper.getChatDisplayName(chat),  // Usar helper para obtener nombre
                    description: chat.description || null,
                    unread_count: unreadCount,
                    last_message: messages[0] ? {
                        text: messages[0].body,
                        timestamp: messages[0].timestamp
                    } : null
                };
                
                // Obtener foto de perfil del grupo
                groupInfo.profile_picture_url = await chatHelper.getProfilePicture(chat);
                
                // Obtener participantes usando helper
                try {
                    console.log(`[API /api/groups] Getting participants for group ${chat.id._serialized}...`);
                    const participants = await chatHelper.getGroupParticipants(config.client, chat);
                    console.log(`[API /api/groups] Participants retrieved:`, participants.length);
                    
                    groupInfo.participants = participants.map(p => ({
                        id: p.id,
                        phone: p.phone,
                        formattedPhone: p.formattedPhone,
                        name: p.name,
                        pushname: p.pushname,
                        displayName: p.displayName,
                        isAdmin: p.isAdmin,
                        profile_picture_url: p.profilePictureUrl
                    }));
                    groupInfo.participants_count = participants.length;
                    console.log(`[API /api/groups] Group ${chat.id._serialized} processed successfully with ${groupInfo.participants_count} participants`);
                } catch (e) {
                    console.error(`[API /api/groups] Error getting participants for group ${chat.id._serialized}:`, e);
                    groupInfo.participants = [];
                    groupInfo.participants_count = 0;
                }
                
                groupsData.push(groupInfo);
            } catch (error) {
                console.error(`Error processing group ${chat.id._serialized}:`, error);
                groupsData.push({
                    chat_id: chat.id._serialized,
                    name: chat.name || 'Unknown Group',
                    description: null,
                    unread_count: 0,
                    last_message: null,
                    participants: [],
                    participants_count: 0
                });
            }
        }
        
        console.log('[API /api/groups] Groups found:', groupsData.length);
        console.log('[API /api/groups] Successfully processed', groupsData.length, 'groups');
        console.log('[API /api/groups] Returning response with groups:', groupsData.map(g => ({ id: g.chat_id, name: g.name })));
        res.json({ groups: groupsData });
    } catch (error) {
        console.error('[API /api/groups] Error getting groups:', error);
        console.error('[API /api/groups] Error stack:', error.stack);
        res.status(500).json({ error: 'Error getting groups', details: error.message });
    }
});

/**
 * GET /api/group-info/:groupId
 * Get detailed information about a specific group
 */
router.get('/api/group-info/:groupId', async (req, res) => {
    if (!config.isReady) return res.status(503).json({ error: 'WhatsApp no listo' });
    
    const { groupId } = req.params;
    
    try {
        const chat = await config.client.getChatById(groupId);
        
        if (!chat.isGroup) {
            return res.status(400).json({ error: 'Chat is not a group' });
        }
        
        let unreadCount = 0;
        try {
            if (typeof chat.getUnreadCount === 'function') {
                unreadCount = await chat.getUnreadCount();
            }
        } catch (_e) {
            /* ignore */
        }
        
        let messages = [];
        try {
            messages = await chat.fetchMessages({ limit: 1 });
        } catch (e) {
            // fetchMessages puede fallar
        }
        
        // Obtener participantes usando helper
        const participants = await chatHelper.getGroupParticipants(config.client, chat);
        
        // Obtener foto de perfil
        const profilePictureUrl = await chatHelper.getProfilePicture(chat);
        
        const groupInfo = {
            chat_id: chat.id._serialized,
            name: chatHelper.getChatDisplayName(chat),
            description: chat.description || null,
            profile_picture_url: profilePictureUrl,
            unread_count: unreadCount,
            last_message: messages[0] ? {
                text: messages[0].body,
                timestamp: messages[0].timestamp
            } : null,
            participants: participants.map(p => ({
                id: p.id,
                phone: p.phone,
                formattedPhone: p.formattedPhone,
                name: p.name,
                pushname: p.pushname,
                displayName: p.displayName,
                isAdmin: p.isAdmin,
                profile_picture_url: p.profilePictureUrl
            })),
            participants_count: participants.length
        };
        
        res.json(groupInfo);
    } catch (error) {
        console.error('Error getting group info:', error);
        res.status(500).json({ error: 'Error getting group info', details: error.message });
    }
});

module.exports = router;
 