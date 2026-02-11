from abc import ABC, abstractmethod

from app.domain.entities import ReceiptItem, ReceiptRef


class ReceiptProvider(ABC):
    @abstractmethod
    def parse(self, payload: str) -> ReceiptRef:
        raise NotImplementedError

    @abstractmethod
    async def fetch_items(self, ref: ReceiptRef) -> list[ReceiptItem]:
        raise NotImplementedError
