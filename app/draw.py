import random
from collections import Counter


class DrawError(Exception):
    pass


def draw(ids: list[str], groups: dict[str, str | None] | None = None) -> dict[str, str]:
    """Return {giver: receiver}. Nobody draws themselves or someone from the same group."""
    groups = groups or {}
    if len(ids) < 3:
        raise DrawError("São precisos pelo menos 3 participantes.")
    if len(set(ids)) != len(ids):
        raise DrawError("Há participantes repetidos.")

    sizes = Counter(g for g in (groups.get(i) for i in ids) if g)
    for group, size in sizes.items():
        if size * 2 > len(ids):
            raise DrawError(
                f"O grupo «{group}» tem {size} pessoas: é impossível que nenhum deles "
                f"tire alguém do mesmo grupo. Reduz o grupo ou junta mais participantes."
            )

    def allowed(giver: str, receiver: str) -> bool:
        if giver == receiver:
            return False
        group = groups.get(giver)
        return not (group and group == groups.get(receiver))

    givers = ids[:]
    random.shuffle(givers)
    # Most constrained first; the shuffle above keeps ties random.
    givers.sort(key=lambda g: sum(allowed(g, r) for r in ids))

    result: dict[str, str] = {}
    taken: set[str] = set()

    def solve(i: int) -> bool:
        if i == len(givers):
            return True
        giver = givers[i]
        options = [r for r in ids if r not in taken and allowed(giver, r)]
        random.shuffle(options)
        for receiver in options:
            result[giver] = receiver
            taken.add(receiver)
            if solve(i + 1):
                return True
            taken.discard(receiver)
            del result[giver]
        return False

    if not solve(0):
        raise DrawError("Não foi possível fazer o sorteio com estas restrições.")
    return result
