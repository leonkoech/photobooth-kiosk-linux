const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
    on: (channel, callback) => {
        ipcRenderer.on(channel, callback);
    },
    send: (channel, args) => {
        ipcRenderer.send(channel, args);
    }
});

// This way, we can call window.electronAPI.on on Next.JS components to handle IPC data that comes from the "back-end" of our application, and window.electronAPI.send to send data to the "back-end" of our application.