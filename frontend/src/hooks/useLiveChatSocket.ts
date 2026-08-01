import { useEffect, useRef, useState } from "react";

const WS_BASE_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";

// TODO: send/receive real Message payloads (see backend/routers/livechat.py) once the
// Live Chat UI is built; this hook only wires the connection lifecycle for now.
export function useLiveChatSocket(sessionId: number | null) {
  const socketRef = useRef<WebSocket | null>(null);
  const [messages, setMessages] = useState<unknown[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (sessionId === null) return;

    const socket = new WebSocket(`${WS_BASE_URL}/ws/livechat/${sessionId}`);
    socketRef.current = socket;

    socket.onopen = () => setIsConnected(true);
    socket.onclose = () => setIsConnected(false);
    socket.onmessage = (event) => {
      setMessages((prev) => [...prev, JSON.parse(event.data)]);
    };

    return () => socket.close();
  }, [sessionId]);

  const send = (payload: unknown) => {
    socketRef.current?.send(JSON.stringify(payload));
  };

  return { messages, isConnected, send };
}
