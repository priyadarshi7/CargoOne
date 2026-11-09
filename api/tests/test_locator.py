from app.ai.locator import place
from app.ai.providers.local import Line


def L(i, text, x, y, w=0.3, h=0.03):
    return Line(id=i, text=text, conf=0.9, x=x, y=y, w=w, h=h)


LINES = [
    L(0, "LR/MH20/26-27/900019", 0.1, 0.12),
    L(1, "Date 08/11/2026", 0.6, 0.2),
    L(2, "1 Cement 50 2.5 2.5t", 0.1, 0.45),
    L(3, "Remarks:", 0.1, 0.7, w=0.1),
    L(4, "Sand short 0.5t", 0.1, 0.74),
]
AI = {"is_document": True, "lr_no": "LR/MH20/26-27/900019", "delivery_date": "2026-11-08", "items": [{"name": "Cement", "quantity": 2.5, "unit": "t"}],
      "quantity_received": "2.5 t", "remarks": "Sand short 0.5 t"}


def test_each_value_the_ai_read_gets_a_box_on_the_line_that_holds_it():
    got = {b.field: b for b in place(AI, LINES, "LR/MH20/26-27/900019")}
    assert set(got) == {"lr_no", "delivery_date", "quantity_received", "remarks"}
    assert got["lr_no"].y == 0.12 and got["delivery_date"].y == 0.2 and got["quantity_received"].y == 0.45 and got["remarks"].y == 0.74


def test_a_value_that_is_not_on_the_paper_gets_no_box():
    got = {b.field for b in place({**AI, "lr_no": "LR/XX/1/999", "delivery_date": "2026-01-01", "remarks": None}, LINES, "LR/XX/1/999")}
    assert "lr_no" not in got and "delivery_date" not in got and "remarks" not in got
