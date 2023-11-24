import dataclasses
import datetime
import enum
import itertools
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import jinja2
import requests
from bs4 import BeautifulSoup

MENSA_URL = (
    "https://www.sw-ka.de/de/hochschulgastronomie/speiseplan/mensa_adenauerring/"
)
MRI_URL = "https://casinocatering.de/speiseplan/"

USER_AGENT = "mensaman/0.1.0"


class Diet(enum.Enum):
    PORK = "pork"
    BEEF = "beef"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"


@dataclass
class Meal:
    diet: Diet | None
    name: str
    price: int | None


@dataclass
class Line:
    name: str
    meals: list[Meal]


def extract_kit_diet(row):
    icon = row.find("td", class_="mtd-icon").find("img")
    if icon is None:
        return None
    icon_src = icon["src"]
    if "rindfleisch" in icon_src:
        return Diet.BEEF
    elif "schweinefleisch" in icon_src:
        return Diet.PORK
    elif "vegetarisch" in icon_src:
        return Diet.VEGETARIAN
    elif "vegan" in icon_src:
        return Diet.VEGAN


def extract_kit_price(row):
    # 1 = students, 3 = employees
    price_text = row.find("span", class_="price_3")
    price = re.search("\\d+,\\d+", price_text.get_text())
    if price is None:
        return None
    return int(price.group().replace(",", ""))


def retrieve_mensa_kit():
    with requests.get(MENSA_URL, headers={"user-agent": USER_AGENT}) as netcon:
        html_source = netcon.content
    soup = BeautifulSoup(html_source, features="html.parser")
    lines = []

    # The current day is always day_1
    today = soup.find("div", id="canteen_day_1")
    for line in today.find_all("tr", class_="mensatype_rows"):
        line_name = line.find("td", class_="mensatype").get_text()

        lobj = Line(line_name, [])

        for row in line.find_all("tr", class_=re.compile("^mt-")):
            name = row.find("td", class_="menu-title").find("span").get_text()
            diet = extract_kit_diet(row)
            price = extract_kit_price(row)
            lobj.meals.append(Meal(diet, name, price))

        lines.append(lobj)

    return lines


def clean_kit_mensa(all_lines):
    cleaned = []
    hidden_lines = {
        "Linie 4",
        "Burgerbar",
        "Linie 6",
        "Spätausgabe",
        "[kœri]",
        "Cafeteria",
        "werkPasta",
        "werkSalate",
    }
    for line in all_lines:
        # We skip the lines that are always the same
        if any(hidden_line in line.name for hidden_line in hidden_lines):
            continue
        clean_line = dataclasses.replace(line, meals=[])
        # Strip off the "Gut & Günstig" or "Vegane Linie"
        if "Linie 1" in clean_line.name or "Linie 2" in clean_line.name:
            clean_line.name = clean_line.name[:7]
        # Strip off the "Pizaz 11-14 Uhr"
        if "[pizza]" in clean_line.name:
            clean_line.name = clean_line.name[:11]
        for meal in line.meals:
            # We skip meals that have no price (usually it's just additional
            # information like "for each meal we add a salad")
            if meal.price is None:
                continue
            clean_line.meals.append(meal)
        cleaned.append(clean_line)
    return cleaned


def retrieve_mri():
    with requests.get(MRI_URL, headers={"user-agent": USER_AGENT}) as netcon:
        html_source = netcon.content
    soup = BeautifulSoup(html_source, features="html.parser")
    today = datetime.date.today()
    result = []

    weekdays = {
        "Montag",
        "Dienstag",
        "Mittwoch",
        "Donnerstag",
        "Freitag",
    }
    weekday_counter = itertools.count()

    for card in soup.find_all(
        "div", class_="elementor-widget-wrap elementor-element-populated"
    ):
        heading = card.find("div", class_="elementor-widget-heading")
        if not heading:
            continue
        if not any(weekday in heading.get_text() for weekday in weekdays):
            continue

        # At this point, we have a card with the meal plan. Let's get the one for today!
        if next(weekday_counter) != today.weekday():
            continue

        meals = card.find("div", class_="elementor-widget-icon-list").find_all("li")
        for meal in meals:
            meal_name = meal.find("span", class_="elementor-icon-list-text").get_text()
            meal_name = meal_name.lstrip("•").strip()
            result.append(Meal(None, meal_name, None))

    return result


def render(lines_kit, meals_mri):
    loader = jinja2.PackageLoader(__name__, "templates")
    env = jinja2.Environment(loader=loader, autoescape=True)
    env.globals["Diet"] = Diet
    template = env.get_template("mensaman.jinja2")
    print(
        template.render(
            lines_kit=lines_kit, meals_mri=meals_mri, now=datetime.datetime.now()
        )
    )


def cli():
    from pprint import pprint

    lines_kit = clean_kit_mensa(retrieve_mensa_kit())
    meals_mri = retrieve_mri()
    render(lines_kit, meals_mri)
