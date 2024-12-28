from flask import Flask, Response
from ics import Calendar, Event
from datetime import datetime, timedelta
from typing import List
from bs4 import BeautifulSoup
import pytz
import requests

# Function to parse HTML and generate a list of Event objects
def parse_html_to_events_from_url(url: str) -> List[Event]:
    # Fetch the HTML content from the URL
    response = requests.get(url)
    response.raise_for_status()  # Raise an error for HTTP issues
    html_stream = response.text

    soup = BeautifulSoup(html_stream, "html.parser")
    events = []

    # Locate the table containing the data
    table = soup.find("table", class_="tableborder")
    if not table:
        return events

    # Extract rows from the table
    rows = table.find_all("tr")[1:]  # Skip header row
    london_tz = pytz.timezone("Europe/London")
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

        # Parse dates with timezone
        try:
            start = london_tz.localize(datetime.strptime(from_date, "%d/%m/%Y"))
            end = london_tz.localize(datetime.strptime(to_date, "%d/%m/%Y"))
        except ValueError:
            continue

        # Create an Event object
        event = Event()
        event.name = f"{suspension_type} - {street_name}"
        event.begin = start
        event.end = end
        event.description = suspension_reason
        event.location = location
        events.append(event)

    return events

# Create Flask app
app = Flask(__name__)

@app.route('/calendar.ics')
def serve_calendar() -> Response:
    # Parse events from the given URL
    url = "https://blah.com/input.html"
    events = parse_html_to_events_from_url(url)

    # Create an ICS calendar
    calendar = Calendar()
    for event in events:
        calendar.events.add(event)

    # Convert calendar to ICS string using the Calendar's "serialize" method
    ics_content = calendar.serialize()

    # Serve the ICS file as a response
    return Response(ics_content, mimetype='text/calendar', headers={"Content-Disposition": "attachment; filename=calendar.ics"})

if __name__ == '__main__':
    app.run(debug=True)
