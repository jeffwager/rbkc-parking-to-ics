from flask import Flask, Response, request
from ics import Calendar, Event
from datetime import datetime, timedelta
from typing import List
from bs4 import BeautifulSoup
import pytz
import requests

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

# Create Flask app
app = Flask(__name__)

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

if __name__ == '__main__':
    app.run(debug=True)
