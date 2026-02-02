// Configuration and global state
module.exports = {
    PORT: process.env.PORT || 3001,
    DJANGO_API_URL: process.env.DJANGO_API_URL || 'http://localhost:8000',
    
    // Global state (will be initialized in services/whatsappClient.js)
    client: null,
    isReady: false,
    currentQR: null,
    
    // Setters for state
    setClient: function(newClient) {
        this.client = newClient;
    },
    
    setIsReady: function(ready) {
        this.isReady = ready;
    },
    
    setCurrentQR: function(qr) {
        this.currentQR = qr;
    }
};

