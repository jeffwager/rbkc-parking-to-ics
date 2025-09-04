from flask import Flask, Response, request
from ics import Calendar, Event
from datetime import datetime, timedelta, timezone
from typing import List
from bs4 import BeautifulSoup
import pytz
import requests
import re
import json
from urllib.parse import quote


# Create Flask app
app = Flask(__name__)


# Function to parse HTML and generate a list of Event objects
def parse_html_to_events_from_url(url: str) -> List[Event]:
    # Fetch the HTML content from the URL using a GET request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    response = requests.get(url, headers=headers)

    # If the request fails, return the exact output from the server
    if not response.ok:
        raise ValueError(f"HTTP Error {response.status_code}: {response.text}")

    html_stream = response.text

    soup = BeautifulSoup(html_stream, "html.parser")
    events = []

    # Locate the table containing the data
    table = soup.find("table", class_="tableborder")
    if not table:
        return events

    # Extract rows from the table
    rows = table.find_all("tr")[1:]  # Skip header row
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        # Extract event details
        street_name = cells[0].get_text(strip=True)
        location = cells[1].get_text(strip=True)
        suspension_type = cells[2].get_text(strip=True)
        suspension_reason = cells[3].get_text(strip=True)
        from_date = cells[4].get_text(strip=True)
        to_date = cells[5].get_text(strip=True)

        # Parse dates
        try:
            start = datetime.strptime(from_date, "%d/%m/%Y").date()
            end = datetime.strptime(to_date, "%d/%m/%Y").date()
        except ValueError:
            continue

        # Create an all-day Event object
        event = Event()
        event.name = f"{suspension_type} - {street_name}"
        event.begin = start
        event.end = end  # No need to add 1 day; ICS library handles exclusive end date for all-day events
        event.make_all_day()
        event.description = suspension_reason
        event.location = location
        events.append(event)

    return events

@app.route('/calendar.ics')
def serve_calendar() -> Response:
    # Get the street names from query parameters (supports multiple values)
    streets = request.args.getlist("street")
    if not streets:
        return Response("Missing 'street' parameter(s)", status=400)

    # Calculate yesterday's date
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime("%Y%m%d")

    # Parse events from the given URL for each street
    base_url = "https://www.rbkc.gov.uk/parking/suspensionresults.asp"
    all_events = []
    for street in streets:
        url = f"{base_url}?Street={street}&Date={date_str}"
        try:
            all_events.extend(parse_html_to_events_from_url(url))
        except ValueError as e:
            return Response(str(e), status=500)

    # Create an ICS calendar
    calendar = Calendar()
    for event in all_events:
        calendar.events.add(event)

    # Convert calendar to ICS string using the Calendar's "serialize" method
    ics_content = calendar.serialize()

    # Serve the ICS file as a response
    return Response(ics_content, mimetype='text/calendar', headers={"Content-Disposition": "attachment; filename=calendar.ics"})


def _parse_iso_utc(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def parse_timetable(js: str) -> Calendar:
    """
    Extract JSON from JS variable and create calendar.
    Looks for: var timetableData = { ... };
    """
    match = re.search(r"var\s+timetableData\s*=\s*(\{.*?\});", js, re.DOTALL)
    if not match:
        raise ValueError("timetableData not found in JS")

    data = json.loads(match.group(1))
    cal = Calendar()

    for entry in data.get("timetables", []):
        ev = Event()
        ev.name = entry.get("name") or "Lesson"
        ev.begin = _parse_iso_utc(entry["startTime"])
        ev.end = _parse_iso_utc(entry["endTime"])
        ev.location = entry.get("location")
        desc_parts = []
        if entry.get("staffName"):
            desc_parts.append(entry["staffName"])
        if desc_parts:
            ev.description = " | ".join(desc_parts)
        cal.events.add(ev)
    return cal


def fetch_timetable(login: str, password: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    session = requests.Session()

    login_data = {'client_id': login, 'client_secret': password, 'set_session_variables': 'true', 'stay_logged_in': False}

    r = session.post("https://bat.msp.thomas-s.co.uk/api/auth", data=quote(json.dumps(login_data)), headers=headers)
    r.raise_for_status()
    j = json.loads(r.text)
    if not j.get('success', False):
        raise ValueError(f"Excepted success, got: {r.text}")

    r = session.get("https://bat.msp.thomas-s.co.uk/showme/timetable", headers=headers)
    r.raise_for_status()
    # print(r.text)
    return r.text


@app.route("/tomcal.ics")
def serve_tomcal():
    login = request.args.get("l")
    password = request.args.get("p")
    if not login or not password:
        return Response("Missing login or password", status=400)

    html = fetch_timetable(login, password)
    cal = parse_timetable(html)
    ics = cal.serialize()

    return Response(ics, mimetype="text/calendar", headers={"Content-Disposition": "attachment; filename=tomcal.ics"})


if __name__ == '__main__':
    app.run(debug=True)
