# Playing around to learn Billogram api

import argparse
import csv
import re
from typing import Dict, Iterable, List, Union

import httpx

from config import load_config

base_url = "https://sandbox.billogram.com/api/v2"

AddressData = Dict[str, str]
ContactData = Dict[str, str]
CustomerData = dict
ItemData = Dict[str, str]
InvoiceData = Dict[str, Union[str, CustomerData, List[ItemData], dict]]

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


def parse_address(rowdata: dict) -> AddressData:
    """
    Get primary address information from the provided data row.
    """
    return {
        "street_address": rowdata["street_address"],
        "zipcode": rowdata["postal_code"],
        "city": rowdata["city"],
    }


def parse_contact(rowdata: dict) -> ContactData:
    """
    Get customer contact information from provided data row.
    """
    return {
        "email": rowdata["email"],
        "phone": rowdata["phone_number"],
        "name": rowdata["name"],
    }


def parse_customer(rowdata: dict) -> CustomerData:
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


def parse_item(rowdata: dict) -> ItemData:
    """
    Get credited item information from provided data row.
    """
    return {
        "title": rowdata["article_name"],
        "price": rowdata["article_price"],
    }


def sanitize_item(item: ItemData) -> None:
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


def pick_send_method(customer: CustomerData) -> str:
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


def process_invoices(client: httpx.Client, file: Iterable[str], create_customers=False):
    """
    Process all invoices present in the provided file.
    """
    for row in csv.DictReader(file):
        customer = parse_customer(row)
        customer_name = customer["name"]
        if create_customers:
            response = client.post("/customer", json=customer)
            if not validate_response(response, "creating customer " + customer_name):
                continue

        item = parse_item(row)
        sanitize_item(item)
        invoice: InvoiceData = {
            "invoice_no": row["invoice_number"],
            "customer": {"customer_no": customer["customer_no"]},
            "items": [item],
        }
        response = client.post("/billogram", json=invoice)
        if not validate_response(response, "creating invoice for " + customer_name):
            continue

        invoice_id = response.json()["data"]["id"]
        payload = {"method": pick_send_method(customer)}
        response = client.post(f"/billogram/{invoice_id}/command/send", json=payload)
        if validate_response(response, "sending invoice to " + customer_name):
            print("Sent invoice to" + customer_name)


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

    with httpx.Client(auth=auth, base_url=base_url) as client:
        for filename in args.files:
            with open(filename) as file:
                process_invoices(client, file, create_customers=not args.skip_customers)
