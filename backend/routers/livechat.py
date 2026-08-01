from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import SessionSource, UserRole
from backend.core.mysql_client import get_db
from backend.models.user import User
from backend.repositories.chat_session import create_session
from backend.repositories.livechat_request import accept_request, create_request, list_waiting_requests
from backend.schemas.chat_session import ChatSessionCreate
from backend.schemas.livechat_request import LiveChatRequestCreate, LiveChatRequestResponse

router = APIRouter(tags=["Live Chat"])


class LiveChatConnectionManager:
    """In-memory WebSocket registry, keyed by chat_session id.

    TODO: swap for a broker-backed implementation (e.g. Redis pub/sub) once running multiple
    backend instances, since this in-process dict does not fan out across processes.
    """

    def __init__(self) -> None:
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, session_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: int, websocket: WebSocket) -> None:
        if session_id in self._connections:
            self._connections[session_id].remove(websocket)

    async def broadcast(self, session_id: int, message: dict) -> None:
        for connection in self._connections.get(session_id, []):
            await connection.send_json(message)


manager = LiveChatConnectionManager()


@router.post("/livechat/request", response_model=LiveChatRequestResponse, status_code=status.HTTP_201_CREATED)
async def request_livechat(payload: LiveChatRequestCreate, db: Session = Depends(get_db)) -> LiveChatRequestResponse:
    """Customer requests to connect with an online Sale (CLAUDE.md §6.3.c)."""
    return create_request(db, customer_id=payload.customer_id)


@router.get(
    "/livechat/requests",
    response_model=list[LiveChatRequestResponse],
    dependencies=[Depends(require_role(UserRole.SALE))],
)
async def list_pending_requests(db: Session = Depends(get_db)) -> list[LiveChatRequestResponse]:
    return list_waiting_requests(db)


@router.post(
    "/livechat/{request_id}/accept",
    response_model=LiveChatRequestResponse,
    dependencies=[Depends(require_role(UserRole.SALE))],
)
async def accept_livechat(
    request_id: int, db: Session = Depends(get_db), sale: User = Depends(require_role(UserRole.SALE))
) -> LiveChatRequestResponse:
    """Sale bấm 'Chấp nhận' — opens a ChatSession backing the Live Chat window (CLAUDE.md §6.4.c)."""
    session = create_session(
        db, sale_id=sale.id, schema=ChatSessionCreate(source=SessionSource.LIVE_CHAT)
    )
    try:
        return accept_request(db, request_id=request_id, sale_id=sale.id, session_id=session.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.websocket("/ws/livechat/{session_id}")
async def livechat_ws(websocket: WebSocket, session_id: int) -> None:
    """Real-time channel shared by Customer and Sale for a given session.

    TODO: authenticate the WebSocket handshake (customer_id or sale JWT) and, per CLAUDE.md §6.4.e,
    route Sale-authored messages carrying requires_hitl=True through the HITL confirm step before
    they are broadcast to the customer.
    """
    await manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await manager.broadcast(session_id, data)
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
