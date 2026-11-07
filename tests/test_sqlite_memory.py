from sally_cibote.memory.sqlite_store import LongTermMemory


def test_schema_and_roundtrip(tmp_path):
    mem = LongTermMemory(tmp_path / "sally_memory.db")
    assert mem.count() == 0
    mid = mem.add("Daniel: marcar amanha dentista", tag="reminder")
    assert mid > 0
    mem.remember_exchange("que horas sao", "Sao 16 horas.")
    assert mem.count() >= 3
    rows = mem.recent(limit=5)
    assert rows
    assert all(hasattr(r, "tag") for r in rows)


def test_search_finds_reminder(tmp_path):
    mem = LongTermMemory(tmp_path / "sally_memory.db")
    mem.remember_exchange("marcar amanha reuniao com joao", "Anotado: reuniao com joao amanha.")
    hits = mem.search("reuniao amanha")
    assert hits
    blob = " ".join(h.content.lower() for h in hits)
    assert "reuniao" in blob or "joao" in blob


def test_search_accent_and_old_reminder(tmp_path):
    mem = LongTermMemory(tmp_path / "old.db")
    mem.add("Daniel: marcar amanha reuniao as 10", tag="reminder")
    mem.add("Combinado: amanha reuniao as 10", tag="fact")
    # Flood recent window with unrelated chatter + poisoned question reminders
    for i in range(90):
        mem.add(f"Daniel: ruido {i}", tag="user")
        mem.add(f"Sally: JA {i}", tag="sally")
    for _ in range(5):
        mem.add("Daniel: o que temos amanha?", tag="reminder")
        mem.add("Sally: nada marcado", tag="sally")
    hits = mem.search("o que temos amanhã?")
    assert hits[0].tag in ("fact", "reminder")
    assert "reuniao" in hits[0].content.lower() or "combinado" in hits[0].content.lower()
    ctx = mem.context_for_prompt("o que temos amanhã?")
    assert "10" in ctx
    assert ctx.lower().index("combinado") < ctx.lower().index("o que temos")


def test_context_for_prompt(tmp_path):
    mem = LongTermMemory(tmp_path / "m.db")
    mem.remember_exchange("meu nome é Daniel", "Oi Daniel.")
    ctx = mem.context_for_prompt("qual meu nome")
    assert "Daniel" in ctx
