# HPXML to RESO Data Dictionary Translator



## Installation

### Prerequisites
- [Python 2.7](https://www.python.org/downloads/), with the following packages:
  - [lxml](http://lxml.de/)
  - [requests](http://docs.python-requests.org/en/latest/)

Use `pip` to install the libraries after you've installed Python. 

```
pip install lxml
pip instal requests
```

If you're using Windows, you can get precompiled binaries of both packages from [this site](http://www.lfd.uci.edu/~gohlke/pythonlibs/) and [install them as described here](https://pip.pypa.io/en/latest/user_guide/#installing-from-wheels).

### Getting the script

Use git to clone it or just download the zip file.

### External API keys

This script uses one or two external APIs to handle the address parsing. You will need to provide the API keys you get from each  in a file called `hpxml2reso.cfg`. There is an template configuration file you can fill out and save at `hpxml2reso-example.cfg`.

- [Texas A&M Geoservices Address Normalization](http://geoservices.tamu.edu/Services/AddressNormalization/). Required. This separates the address into all the parts that RESO requires, but doesn't check that the address actually exists in the real world.
- [Google Maps](https://developers.google.com/maps/documentation/geocoding/get-api-key). Optional. This can be skipped if you're confident your addresses are clean and accurate.

Both have somewhat generous free tiers, which should allow you enough leeway to play around with it. Also, this script caches lookups locally so you won't get dinged for looking up the same address over and over again while you develop. 

## How to Use

Call `python hpxml2reso.py -h` to get a description of the command line arguments it accepts:

```
usage: Convert HPXML to RESO-ish json [-h] [-o OUTFILE] [--bldg_id BLDG_ID]
                                      [--googlemaps]
                                      infile

positional arguments:
  infile

optional arguments:
  -h, --help            show this help message and exit
  -o OUTFILE, --outfile OUTFILE
                        json file to write output to, default stdout
  --bldg_id BLDG_ID     HPXML BuildingID to translate, default first one
  --googlemaps          Use Google Maps API to look up the address in the
                        HPXML file.

```

Calling the script with some HPXML input data returns a json file that has the same fields as the RESO data dictionary.

```
$ python hpxml2reso.py example1.xml
{
    "StreetNumber": "123", 
    "StreetNumberNumeric": "123", 
    "StreetDirPrefix": "W", 
    "StreetName": "Main", 
    "StreetSuffix": "ST", 
    "StreetDirSuffix": "", 
    "UnitNumber": "", 
    "City": "Golden", 
    "StateOrProvince": "CO", 
    "PostalCode": "80401", 
    "LivingArea": 2400.0, 
    "LivingAreaUnits": "Square Feet", 
    "LivingAreaSource": null, 
    "WalkScore": 37, 
    "GreenVerification": {
        "DOEHomeEnergyScore": {
            "Body": "US DOE", 
            "Year": 2015, 
            "Metric": 8, 
            "URL": null
        }
    }, 
    "Heating": [
        "Electric Radiant Floor, 95 AFUE", 
        "Air-to-air Heat Pump, 8 HSPF"
    ], 
    "Cooling": [
        "Central Air Conditioning, 13 SEER", 
        "Air-to-air Heat Pump, 15 SEER"
    ]
}

```