from monitor.parser import extract_eta, classify_page
import pytest

STOP = {
    "page_stop_name": "Улица Эшона Бабаханова",
    "buses": [
        {"route": "29", "destination": "Пахтакор", "direction_label": "Metro Paxtakor"},
        {"route": "72", "destination": "Чорсу", "direction_label": "Chorsu"},
    ],
}

TEXT = """Улица Эшона Бабаханова
Остановка общественного транспорта
Автобусы
29
Прогноз прибытия
29
до «Метро Пахтакор»
14 мин
72
до «Чорсу»
прибывает
Полное расписание
"""


def test_eta():
    assert extract_eta(TEXT, "29", "Пахтакор") == "14 daqiqa"
    assert classify_page(TEXT, "https://yandex.uz/maps/", STOP) == (
        "ok", [
            {"route": "29", "destination": "Пахтакор", "eta": "14 daqiqa"},
            {"route": "72", "destination": "Чорсу", "eta": "yetib kelmoqda"},
        ]
    )


def test_wrong_direction_and_route():
    assert extract_eta(TEXT, "29", "Чорсу") is None
    assert extract_eta(TEXT, "30", "Пахтакор") is None


def test_approaching_and_none():
    assert extract_eta(TEXT.replace("14 мин", "прибывает"), "29", "Пахтакор") == "yetib kelmoqda"
    assert classify_page(TEXT.replace("14 мин", "").replace("прибывает", ""), "https://yandex.uz/maps/", STOP)[0] == "no_eta"


def test_same_route_in_two_directions():
    page = TEXT.replace("72\nдо «Чорсу»", "29\nдо «Чорсу»")
    assert extract_eta(page, "29", "Чорсу") == "yetib kelmoqda"


def test_one_bus_missing_eta_keeps_other_result():
    page = TEXT.replace("прибывает", "")
    assert classify_page(page, "https://yandex.uz/maps/", STOP) == (
        "ok", [
            {"route": "29", "destination": "Пахтакор", "eta": "14 daqiqa"},
            {"route": "72", "destination": "Чорсу", "eta": None},
        ]
    )


@pytest.mark.parametrize("route,destination,frequency", [
    ("152", "Финансовый лицей", "Каждые\n18 мин"),
    ("35", "Детская инфекционная больница № 5", "Каждую\n21 мин"),
])
def test_service_frequency_is_not_arrival_eta(route, destination, frequency):
    page = (
        f"Улица Бахор\nПрогноз прибытия\n{route}\n"
        f"до «{destination}»\n{frequency}\nПолное расписание"
    )
    assert extract_eta(page, route, destination) is None


def test_limited_captcha_wrong_page():
    assert classify_page("limited", "https://yandex.uz/maps", STOP)[0] == "limited"
    assert classify_page("Я не робот", "https://yandex.uz/maps", STOP)[0] == "captcha"
    assert classify_page("Other stop page", "https://yandex.uz/maps", STOP)[0] == "wrong_page"
