# Comment ajouter un tool

1. Créez un module dans `app/catalog/tools/<nom>.py` : une logique pure, sans accès au réseau ni à la base.
2. Exposez une fonction publique qui renvoie `ok(...)` en cas de succès, ou lève `ToolError(code, message)` en cas d'erreur.
3. Recevez l'horloge en paramètre (`clock: Clock`) : n'appelez jamais `datetime.now()` directement.
4. Validez les entrées avec `require(...)` et les bornes de `bounds.py` (`MAX_DATE_RANGE_YEARS`, `MAX_LIST_ITEMS`).
5. Les codes d'erreur sont en minuscules (`date_invalide`), les messages en français, lisibles par l'agent.
6. Écrivez les tests dans `tests/test_<nom>.py`, avec `FixedClock` pour fixer la date.

## Exemple de l'utilisation du code

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from app.catalog.tools.clock import FixedClock
from app.catalog.tools.errors import ToolError, ok

clock = FixedClock(datetime(2026, 3, 3, 10, 0, tzinfo=ZoneInfo("Europe/Paris")))
clock.now().date()  # 2026-03-03, toujours
ok(date="2026-03-03")  # {"ok": True, "date": "2026-03-03"}
ToolError("date_invalide", "Le 31 février n'existe pas.").to_dict()
```
