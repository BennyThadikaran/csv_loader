import io
import os
from typing import Optional
import pandas as pd
from datetime import datetime
from pathlib import Path


def csv_loader(
    file_path: Path,
    period=160,
    end_date: Optional[datetime] = None,
    chunk_size=1024 * 6,
) -> pd.DataFrame:

    def get_date(start: int, chunk: bytes) -> datetime:
        """Helper function

        Parse the first occurence of a date string in a chunk at the
        given start index

        Raises a ValueError if date is invalid or not found
        """

        # Given the start point date column ends with ','
        end = chunk.find(b",", start)

        date_str = chunk[start:end].decode()

        if len(date_str) > 10:
            date = datetime.strptime(date_str[:16], datetime_fmt)
        else:
            date = datetime.strptime(date_str, date_fmt)

        return date

    size = os.path.getsize(file_path)
    datetime_fmt = "%Y-%m-%d %H:%M"
    date_fmt = "%Y-%m-%d"

    if size <= chunk_size and not end_date:
        return pd.read_csv(
            file_path, index_col="Date", parse_dates=["Date"]
        ).iloc[-period:]

    chunks_read = []  # store the bytes chunk in a list
    start_date = None
    prev_chunk_start_line = None

    # Account for public holdays - 3 holidays every 50 days or atleast 3 days
    # this wont be required for 24x7 markets like Crypto etc
    holiday_offset = max(3, period // 50 * 3)

    if end_date:
        # I used Business day offset (Sat/Sun Off)
        # For 24x7 markets a regular timedelta would suffice
        start_date = end_date - pd.offsets.BDay(period + holiday_offset)

    # Open in binary mode and read from end of file
    with file_path.open(mode="rb") as f:

        # Read the first line of file to get column names
        columns = f.readline()

        curr_pos = size  # set current position to end of file

        while curr_pos > 0:
            read_size = min(chunk_size, curr_pos)

            # Set the current read position in the file
            f.seek(curr_pos - read_size)

            # From the current position read n bytes
            chunk = f.read(read_size)

            # Get N lines upto end_date
            if end_date:
                # First line in a chunk may not be complete line
                # So skip the first line and parse the first date in chunk
                newline_index = chunk.find(b"\n")

                start = newline_index + 1

                current_dt = get_date(start, chunk)

                # start storing chunks once end date has reached
                if current_dt <= end_date:
                    if prev_chunk_start_line:
                        # as we append the first chunk, the last line
                        # may incomplete. We keep a reference to the first line
                        # of the previous chunk and concat it here.
                        chunk = chunk + prev_chunk_start_line
                        prev_chunk_start_line = None

                    if start_date and current_dt <= start_date:
                        # reached starting date
                        # add the columns to chunk and append it
                        chunks_read.append(columns + chunk[start:])
                        break

                    chunks_read.append(chunk)
                else:
                    # Keep a reference to the first line of chunk till we reach
                    # the current date
                    prev_chunk_start_line = chunk[: chunk.find(b"\n")]

            else:
                # Get N lines from end of file

                if curr_pos == size:
                    # On first chunk, get the last date to calculate start_date
                    last_newline_index = chunk[:-1].rfind(b"\n")

                    start = last_newline_index + 1
                    last_dt = get_date(start, chunk)

                    start_date = last_dt - pd.offsets.BDay(
                        period + holiday_offset
                    )

                # First line may not be a complete line.
                # To skip this line, find the first newline character
                newline_index = chunk.find(b"\n")

                start = newline_index + 1

                current_dt = get_date(start, chunk)

                if start_date is None:
                    start_date = datetime.now() - pd.offsets.BDay(
                        period + holiday_offset
                    )

                if current_dt <= start_date:
                    # Concatenate the columns and chunk together
                    # and append to list
                    chunks_read.append(columns + chunk[start:])
                    break

                # we are storing the chunks in bottom first order.
                # This has to be corrected later by reversing the list
                chunks_read.append(chunk)

            curr_pos -= read_size

        if end_date and not chunks_read:
            # If chunks_read is empty, end_date was not found in file
            raise IndexError("Date out of bounds of current DataFrame")

        # Reverse the list and join it into a bytes string.
        # Store the result in a buffer
        buffer = io.BytesIO(b"".join(chunks_read[::-1]))

    df = pd.read_csv(
        buffer,
        parse_dates=["Date"],
        index_col="Date",
    )

    if end_date:
        return df.loc[:end_date].iloc[-period:]
    else:
        return df.iloc[-period:]


if __name__ == "__main__":
    from datetime import datetime

    file_path = Path("./test_data/algousdt.csv")

    df = csv_loader(file_path)
    print(df)

    df = csv_loader(file_path, end_date=datetime(2024, 1, 18, 15, 0))
    print(df)

    df = csv_loader(file_path, period=2, end_date=datetime(2024, 1, 18, 15, 0))
    print(df)
