self.addEventListener("install", (e) => {
  console.log("Service Worker installed");
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  console.log("Service Worker activated");
});

self.addEventListener("push", function (event) {
  const data = event.data.json();
  const title = data.title || "FitTrackMe Reminder";
  const options = {
    body: data.body || "Stay consistent today 💪",
    icon: data.icon || "/static/icons/icon-192x192.png",
    badge: "/static/icons/icon-192x192.png",
  };
  event.waitUntil(self.registration.showNotification(title, options));
});
