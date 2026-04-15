const CONFIG = {
    // Dynamically determine the base path (e.g., "/" or "/app")
    // This works whether you access it via the host proxy (/app/) or directly (port 800)
    API_BASE: window.location.pathname.slice(0, window.location.pathname.lastIndexOf('/'))
};
