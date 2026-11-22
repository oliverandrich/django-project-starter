// Sends Django's CSRF token with every htmx request.
// Read per request, so the header follows login(), which rotates the token in the cookie.
// The token in the page's meta tag covers pages before Django has set the cookie.
document.addEventListener("htmx:config:request", (event) => {
    const cookie = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    const token = cookie?.[1] ?? document.querySelector('meta[name="csrf-token"]')?.content;
    if (token) {
        event.detail.ctx.request.headers["X-CSRFToken"] = token;
    }
});
