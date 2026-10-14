import uuid
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_source import DocumentSource
from app.models.dossier import Dossier, DossierDocument


class SourceNameTakenError(Exception):
    """Une source de ce nom existe déjà dans le même catalogue d'analyse (ou le même dossier, pour un tampon)."""


class DocumentSourceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, source_id: uuid.UUID) -> DocumentSource | None:
        return await self.db.get(DocumentSource, source_id)

    async def list_for_analyse(self, analyse_id: uuid.UUID) -> Sequence[DocumentSource]:
        result = await self.db.execute(
            select(DocumentSource)
            .where(DocumentSource.analyse_id == analyse_id)
            .order_by(DocumentSource.name, DocumentSource.id)
        )
        return result.scalars().all()

    async def list_for_dossier(self, dossier: Dossier) -> Sequence[DocumentSource]:
        """Sources proposées pour ce dossier : celles de son analyse, ou ses tampons s'il est « à ranger »."""
        if dossier.analyse_id is not None:
            return await self.list_for_analyse(dossier.analyse_id)
        result = await self.db.execute(
            select(DocumentSource)
            .where(DocumentSource.dossier_id == dossier.id)
            .order_by(DocumentSource.name, DocumentSource.id)
        )
        return result.scalars().all()

    async def is_available_for(self, dossier: Dossier, source_id: uuid.UUID) -> bool:
        """La source peut-elle être donnée à un document de ce dossier ?"""
        source = await self.get(source_id)
        if source is None:
            return False
        if dossier.analyse_id is not None:
            return source.analyse_id == dossier.analyse_id
        return source.dossier_id == dossier.id

    async def create(
        self,
        *,
        name: str,
        description: str,
        analyse_id: uuid.UUID | None = None,
        dossier_id: uuid.UUID | None = None,
    ) -> DocumentSource:
        source = DocumentSource(name=name, description=description, analyse_id=analyse_id, dossier_id=dossier_id)
        self.db.add(source)
        try:
            await self.db.commit()
        except IntegrityError as error:
            await self.db.rollback()
            raise SourceNameTakenError(name) from error
        await self.db.refresh(source)
        return source

    async def update(self, source: DocumentSource, *, name: str, description: str) -> DocumentSource:
        source.name = name
        source.description = description
        try:
            await self.db.commit()
        except IntegrityError as error:
            await self.db.rollback()
            raise SourceNameTakenError(name) from error
        await self.db.refresh(source)
        return source

    async def delete(self, source: DocumentSource) -> None:
        """Les documents qui l'utilisent restent, sans source (FK `ON DELETE SET NULL`)."""
        await self.db.delete(source)
        await self.db.commit()

    async def promote_dossier_sources(self, dossier_id: uuid.UUID, analyse_id: uuid.UUID) -> None:
        """Rattachement d'un dossier « à ranger » à une analyse : ses sources tampon rejoignent le catalogue de
        l'analyse. Si l'analyse a déjà une source du même nom, on garde celle-là et les documents sont rebranchés
        dessus. Ne valide pas la transaction : l'appelant la termine."""
        tampons = (
            (await self.db.execute(select(DocumentSource).where(DocumentSource.dossier_id == dossier_id)))
            .scalars()
            .all()
        )
        if not tampons:
            return
        existing = {source.name: source for source in await self.list_for_analyse(analyse_id)}
        for tampon in tampons:
            if tampon.name in existing:
                await self.db.execute(
                    update(DossierDocument)
                    .where(DossierDocument.source_id == tampon.id)
                    .values(source_id=existing[tampon.name].id)
                )
                await self.db.delete(tampon)
            else:
                tampon.analyse_id = analyse_id
                tampon.dossier_id = None
        await self.db.flush()
