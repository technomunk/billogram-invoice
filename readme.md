# Billogram invoicing solution test

## Usage

- Go to https://sandbox.billogram.com/
- Create an account
- Create an API User
- Create a [toml](https://github.com/toml-lang/toml) `config.toml` document with follwing fields
	+ `login` with the API user id
	+ `password` with the API user password
- Find a csv file with relevant mock customer data
- Run `python3 invoice.py <csv file>`
