# Playing around to learn Billogram api

import argparse
import asyncio
import csv
import re
from logging import error
from typing import Sequence, Tuple

import httpx

from config import load_config

base_url = "https://sandbox.billogram.com/api/v2"

# http://emailregex.com
EMAIL_RE = re.compile(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)")
PHONE_RE = re.compile(r"0\d{9}")


def validate_response(response: httpx.Response, context: str = "") -> bool:
    """
    Check that response has status code 200 and print an error if it isn't.
    """
    if response.status_code != 200:
        response_msg = response.json()["data"]["message"]
        if context:
            print(f"Error while {context}: {response_msg}")
        else:
            print(f"Error: {response_msg}")
        return False
    return True


def parse_address(rowdata: dict) -> dict:
    """
    Get primary address information from the provided data row.
    """
    return {
        "street_address": rowdata["street_address"],
        "zipcode": rowdata["postal_code"],
        "city": rowdata["city"],
    }


def parse_contact(rowdata: dict) -> dict:
    """
    Get customer contact information from provided data row.
    """
    return {
        "email": rowdata["email"],
        "phone": rowdata["phone_number"],
        "name": rowdata["name"],
    }


def parse_customer(rowdata: dict) -> dict:
    """
    Get customer information from provided data row.
    """
    return {
        "customer_no": rowdata["customer_number"],
        # get  street, post code and city
        "address": parse_address(rowdata),
        # get customer name, phone and email
        "contact": parse_contact(rowdata),
        "name": rowdata["name"],
    }


def parse_item(rowdata: dict) -> dict:
    """
    Get credited item information from provided data row.
    """
    return {
        "title": rowdata["article_name"],
        "price": rowdata["article_price"],
    }


def sanitize_item(item: dict) -> None:
    """
    Make sure the item adheres to format expected by Billogram API.
    Fills required fields with default values.
    Abbreviates long titles moving the full title into description.
    """
    if "vat" not in item:
        item["vat"] = "25"
    if "units" not in item:
        item["unit"] = "unit"
    if "count" not in item:
        item["count"] = "1"
    if len(item["title"]) > 40:
        item["description"] = item["title"]
        item["title"] = "movie"


def is_email(string: str) -> bool:
    """
    Check if the provided string is a valid email address.
    """
    return EMAIL_RE.fullmatch(string) is not None


def is_phone_number(string: str) -> bool:
    """
    Check if the provided string is a valid phone number.
    """
    return PHONE_RE.fullmatch(string) is not None


def pick_send_method(customer: dict) -> str:
    """
    Pick a method of sending the Billogram for the provided customer.

    If possible will use Email if available, falling back to SMS if
    phone number is available, finally using letter otherwise.
    """
    if is_email(customer["contact"]["email"]):
        return "Email"
    elif is_phone_number(customer["contact"]["phone"]):
        return "SMS"
    else:
        return "Letter"


async def process_invoice(client: httpx.AsyncClient, invoice: dict, create_customer: bool) -> None:
    """
    Process a single invoice, populating an entry for it in Billogram and sending it.
    """
    customer = parse_customer(invoice)
    customer_name = customer["name"]
    if create_customer:
        response = await client.post("/customer", json=customer)
        if not validate_response(response, "creating customer " + customer_name):
            return

    item = parse_item(invoice)
    sanitize_item(item)
    billogram = {
        "invoice_no": invoice["invoice_number"],
        "customer": {"customer_no": customer["customer_no"]},
        "items": [item],
    }
    response = await client.post("/billogram", json=billogram)
    if not validate_response(response, "creating invoice for " + customer_name):
        return

    invoice_id = response.json()["data"]["id"]
    payload = {"method": pick_send_method(customer)}
    response = await client.post(f"/billogram/{invoice_id}/command/send", json=payload)
    validate_response(response, "sending invoice to " + customer_name)


async def process_file_invoices(client: httpx.AsyncClient, filename: str, create_customers: bool) -> None:
    """
    Process all invoices present in the file with provided name in parallel.
    """
    print("Processing invoices in " + filename)
    with open(filename) as file:
        invoices = csv.DictReader(file)
        tasks = (process_invoice(client, invoice, create_customers) for invoice in invoices)
        results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            error(result)
    print("Processed invoices in " + filename)


async def process_invoice_files(filenames: Sequence[str], auth: Tuple[str, str], create_customers: bool) -> None:
    """
    Process invoices in files with provided filenames in parallel.
    """
    async with httpx.AsyncClient(auth=auth, base_url=base_url, timeout=30) as client:
        tasks = (process_file_invoices(client, filename, create_customers) for filename in filenames)
        results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            error(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-customers", action="store_true", dest="skip_customers", help="skip creating customer data entries"
    )
    parser.add_argument(
        "files",
        metavar="FILE",
        type=str,
        nargs="+",
        help="filename(s) of csv file with invoice data to process",
    )

    args = parser.parse_args()

    config = load_config("config.toml")
    if not config["login"] or not config["password"]:
        exit("Please provide login details in config.toml")

    auth = (config["login"], config["password"])
    asyncio.run(process_invoice_files(args.files, auth, not args.skip_customers))
