import { io } from "socket.io-client";

// extend window object
declare global {
  interface Window {
    site_name: string;
  }
}

export function initSocket() {
  const siteName = window.site_name || window.location.hostname;
  const url = `${window.location.origin}/${siteName}`;

  const socket = io(url, {
    withCredentials: true,
    reconnectionAttempts: 5,
  });

  return socket;
}

export const socket = initSocket();
