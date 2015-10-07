import sys
import os
import argparse
import ConfigParser
import json
import re
import string
from collections import OrderedDict
import datetime as dt

from lxml import etree
import requests

thisdir = os.path.dirname(os.path.abspath(__file__))
configfile = os.path.join(thisdir, 'hpxml2reso.cfg')
config = ConfigParser.RawConfigParser()
config.read(configfile)

ns = {'h': 'http://hpxmlonline.com/2014/6'}


class GeolocationError(Exception):
    pass


def get_google_address(address, city, state, zip_code):
    google_maps_key = config.get('GoogleMaps', 'key')
    gmaps_geolocation_url = 'https://maps.googleapis.com/maps/api/geocode/json'
    params = {
        'key': google_maps_key,
        'address': ' '.join([address, city, state, zip_code])
    }
    res = requests.get(gmaps_geolocation_url, params=params)
    resjson = res.json()
    if resjson['status'] != 'OK':
        raise GeolocationError('{} - {}'.format(resjson['status'], resjson.get('error_message', '')))
    if not len(resjson['results']) == 1:
        raise GeolocationError('Could not find single location for address: {address}'.format(params))
    return resjson['results'][0]


def get_tamu_address_normalization(address, city, state, zip_code):
    tamu_key = config.get('TAMUGeoServices', 'key')
    url = 'http://geoservices.tamu.edu/Services/AddressNormalization/WebService/v04_01/Rest/'
    params = {
        'apiKey': tamu_key,
        'version': '4.01',
        'nonParsedStreetAddress': address,
        'nonParsedCity': city,
        'nonParsedState': state,
        'nonParsedZip': zip_code,
        'responseFormat': 'json'
    }
    res = requests.get(url, params=params)
    resjson = res.json()
    if not resjson['QueryStatusCode'] == 'Success':
        raise GeolocationError('{}'.format(resjson['QueryStatusCode']))
    if not len(resjson['StreetAddresses']):
        raise GeolocationError('Could not find single location for address: {} {} {} {}'.format(address, city, state, zip_code))
    return resjson['StreetAddresses'][0]


def get_single_xpath_item(el, xpathexpr, astype=None, **kwargs):
    ret_list = el.xpath(xpathexpr, namespaces=ns, **kwargs)
    if len(ret_list) == 1:
        if astype is not None:
            return astype(ret_list[0])
        else:
            return ret_list[0]
    elif len(ret_list) == 0:
        return None
    else:
        assert False


def hpxml2reso(file_in, bldg_id=None):
    """
    Convert an HPXML file into a dict of RESO fields

    :param file_in: file handle or filename of HPXML file
    :return: dict of RESO fields
    """

    # Output dict
    reso = OrderedDict()

    tree = etree.parse(file_in)
    root = tree.getroot()

    # Get a specific building, if requested, otherwise get first one.
    if bldg_id is None:
        bldg = root.xpath('//h:Building[1]', namespaces=ns)[0]
        bldg_id = bldg.xpath('h:BuildingID/@id', namespaces=ns, smart_strings=False)[0]
    else:
        bldg = root.xpath('//h:Building[h:BuildingID/@id=$bldg_id]', bldg_id=bldg_id, namespaces=ns)[0]

    # Get the street address
    # The street address is HPXML is much more simple than what is expected in the RESO Data Dictionary
    address_xml = bldg.xpath('descendant::h:Address[h:AddressType="street"]', namespaces=ns)[0]
    address = ' '.join(address_xml.xpath('h:Address1/text() | h:Address2/text()', namespaces=ns))
    city = address_xml.xpath('h:CityMunicipality/text()', namespaces=ns)[0]
    state = address_xml.xpath('h:StateCode/text()', namespaces=ns)[0]
    zip_code = address_xml.xpath('h:ZipCode/text()', namespaces=ns)[0]

    # It could be potentially useful to use Google Maps API to check the address exists here and clean it up.
    # google_address = get_google_address(address, city, state, zip_code)
    # for item in google_address['address_components']:
    #     if 'street_number' in item['types']:
    #         address = item['long_name']
    #     elif 'route' in item['types']:
    #         address += ' ' + item['long_name']
    #     elif 'locality' in item['types']:
    #         city = item['long_name']
    #     elif 'administrative_area_level_1' in item['types']:
    #         state = item['short_name']
    #     elif 'postal_code' in item['types']:
    #         zip_code = item['long_name']

    # Use Texas A&M's address normalization service to split out all the parts.
    # Their API does a great job of splitting the address up accurately, but doesn't check it against a database
    # of known addresses to verify it exists.
    tamu_address = get_tamu_address_normalization(address, city, state, zip_code)
    reso['StreetNumber'] = ' '.join([tamu_address[x] for x in ('Number', 'NumberFractional')])
    reso['StreetNumberNumeric'] = tamu_address['Number']
    reso['StreetDirPrefix'] = tamu_address['PreDirectional']
    reso['StreetName'] = tamu_address['StreetName']
    reso['StreetSuffix'] = tamu_address['Suffix']
    reso['StreetDirSuffix'] = tamu_address['PostDirectional']
    reso['UnitNumber'] = ' '.join([tamu_address[x] for x in ('SuiteType', 'SuiteNumber')]).strip()
    reso['City'] = tamu_address['City']
    reso['StateOrProvince'] = tamu_address['State']
    reso['PostalCode'] = tamu_address['ZIP']

    # Conditioned Living Area

    reso['LivingArea'] = get_single_xpath_item(bldg, 'descendant::h:BuildingConstruction/h:ConditionedFloorArea/text()', float)
    reso['LivingAreaUnits'] = 'Square Feet'
    reso['LivingAreaSource'] = '????'

    # WalkScore
    walkscore_els = bldg.xpath(
        'descendant::h:EnergyScore[h:ScoreType="other"][h:extension/h:ScoreType="WalkScore"]/h:Score/text()',
        namespaces=ns
    )
    if len(walkscore_els) > 0:
        reso['WalkScore'] = int(walkscore_els[0])

    # HEScore
    hescore_els = bldg.xpath(
        'descendant::h:EnergyScore[h:ScoreType="US DOE Home Energy Score"]',
        namespaces=ns
    )
    if len(hescore_els) > 0:
        hescore_el = hescore_els[0]
        reso['GreenVerification'] = OrderedDict()
        hescore = reso['GreenVerification']['DOEHomeEnergyScore'] = OrderedDict()
        hescore['Body'] = 'US DOE'
        hescore['Year'] = get_single_xpath_item(hescore_el, 'h:extension/h:AssessmentDate/text()', lambda x: dt.datetime.strptime(x, '%Y-%m-%d').year)
        hescore['Metric'] = get_single_xpath_item(hescore_el, 'h:Score/text()', int)
        hescore['URL'] = None

    # Heating
    # See if there's a specified primary system
    htgsys = get_single_xpath_item(
        bldg,
        'descendant::*[h:SystemIdentifier/@id=//h:Building[h:BuildingID/@id=$bldg_id]/descendant::h:PrimaryHeatingSystem/@idref]',
        bldg_id=bldg_id
    )
    # If not, get all of the heating systems (HeatingSystem and HeatPump)
    if htgsys is None:
        htgsys = bldg.xpath('descendant::h:HeatingSystem|descendant::h:HeatPump', namespaces=ns)
        if len(htgsys) == 1:

            # If there's only one, use that.
            htgsys = htgsys[0]

        else:

            # If there's more than one, get some metrics about each to decide which is the primary
            all_htg_sys_metrics = []
            for htg_el in htgsys:
                htg_sys_metrics = {}
                htg_sys_metrics['id'] = htg_el.xpath('h:SystemIdentifier/@id', namespaces=ns)[0]
                htg_sys_metrics['frac_load_served'] = get_single_xpath_item(htg_el, 'h:FractionHeatLoadServed/text()', float)
                htg_sys_metrics['floor_area_served'] = get_single_xpath_item(htg_el, 'h:FloorAreaServed/text()', float)
                htg_sys_metrics['capacity'] = get_single_xpath_item(htg_el, 'h:HeatingCapacity/text()', float)
                all_htg_sys_metrics.append(htg_sys_metrics)

            # Find out which sorting metric all of the systems have
            sort_order_precedence = ['frac_load_served', 'floor_area_served', 'capacity']
            for sort_col in sort_order_precedence:
                has_all_sort_col = True
                for htg_sys_metrics in all_htg_sys_metrics:
                    if htg_sys_metrics[sort_col] is None:
                        has_all_sort_col = False
                        break
                if has_all_sort_col:
                    break

            if not has_all_sort_col:
                # If there's no common metric to sort them by, pick the first one.
                htg_id = all_htg_sys_metrics[0]['id']
            else:
                # Otherwise, find the primary system by sorting by the appropriate metric
                htg_id = sorted(all_htg_sys_metrics, key=lambda x: x[sort_col], reverse=True)[0]['id']

            htgsys = bldg.xpath('descendant::h:*[h:SystemIdentifier/@id=$htg_id]', namespaces=ns, htg_id=htg_id)[0]

    # Get the efficiency information about the heating system
    htg_sys_el_name = htgsys.xpath('name()', namespaces=ns)
    if htg_sys_el_name == 'HeatPump':
        heat_pump_type = get_single_xpath_item(htgsys, 'h:HeatPumpType/text()')
        heat_pump_type = string.capwords(heat_pump_type)
        efficiency = get_single_xpath_item(htgsys, 'h:AnnualHeatEfficiency[1]/h:Value/text()')
        eff_units = get_single_xpath_item(htgsys, 'h:AnnualHeatEfficiency[1]/h:Units/text()')
        if eff_units in ('AFUE', 'Percent'):
            efficiency *= 100
            efficiency = '{:.0f}'.format(efficiency)
        if eff_units == 'Percent':
            eff_units = '% Efficient'
        else:
            eff_units = ' ' + eff_units
        reso['Heating'] = '{} Heat Pump, {}{}'.format(heat_pump_type, efficiency, eff_units)
    elif htg_sys_el_name == 'HeatingSystem':
        htg_sys_type = htgsys.xpath('name(h:HeatingSystemType/h:*)', namespaces=ns)
        # Add spaces between words of the heating system type.
        htg_sys_type = re.sub(r'([a-z])([A-Z])', r'\1 \2', htg_sys_type)
        if htg_sys_type == 'Electric Resistance':
            htg_sys_type = get_single_xpath_item(htgsys, 'h:HeatingSystemType/h:ElectricResistance/h:ElectricDistribution/text()')
            htg_sys_type = string.capwords(htg_sys_type)
        elif htg_sys_type == 'District Steam':
            htg_sys_type = get_single_xpath_item(htgsys, 'h:HeatingSystemType/h:DistrictSteam/h:DistrictSteamType/text()')
        fuel = string.capwords(htgsys.xpath('h:HeatingSystemFuel/text()', namespaces=ns)[0])
        fuel = fuel.replace('Electricity', 'Electric')
        if fuel.find('Fuel Oil') > -1:
            fuel = 'Fuel Oil'
        elif fuel.find('Coal') > -1:
            fuel = 'Coal'
        efficiency = get_single_xpath_item(htgsys, 'h:AnnualHeatingEfficiency[1]/h:Value/text()', float)
        eff_units = get_single_xpath_item(htgsys, 'h:AnnualHeatingEfficiency[1]/h:Units/text()')
        if eff_units in ('AFUE', 'Percent'):
            efficiency *= 100
            efficiency = '{:.0f}'.format(efficiency)
        if eff_units == 'Percent':
            eff_units = '% Efficient'
        else:
            eff_units = ' ' + eff_units
        reso['Heating'] = '{1} {0}, {2}{3}'.format(htg_sys_type, fuel, efficiency, eff_units)
    else:
        assert False

    # Cooling
    # See if there's a specified primary system
    clgsys = get_single_xpath_item(
        bldg,
        'descendant::*[h:SystemIdentifier/@id=//h:Building[h:BuildingID/@id=$bldg_id]/descendant::h:PrimaryCoolingSystem/@idref]',
        bldg_id=bldg_id
    )

    # If not, get all of the heating systems (CoolingSystem and HeatPump)
    if clgsys is None:
        clgsys = bldg.xpath('descendant::h:CoolingSystem|descendant::h:HeatPump', namespaces=ns)
        if len(clgsys) == 1:

            # If there's ony one, use that.
            clgsys = clgsys[0]

        else:

            # If there's more than one, get some metrics about each to decide which is the primary
            all_clg_sys_metrics = []
            for clg_el in clgsys:
                clg_sys_metrics = {}
                clg_sys_metrics['id'] = clg_el.xpath('h:SystemIdentifier/@id', namespaces=ns)[0]
                clg_sys_metrics['frac_load_served'] = get_single_xpath_item(clg_el, 'h:FractionCoolLoadServed/text()', float)
                clg_sys_metrics['floor_area_served'] = get_single_xpath_item(clg_el, 'h:FloorAreaServed/text()', float)
                clg_sys_metrics['capacity'] = get_single_xpath_item(clg_el, 'h:CoolingCapacity/text()', float)
                all_clg_sys_metrics.append(clg_sys_metrics)

            # Find out which sorting metric all of the systems have
            sort_order_precedence = ['frac_load_served', 'floor_area_served', 'capacity']
            for sort_col in sort_order_precedence:
                has_all_sort_col = True
                for clg_sys_metrics in all_clg_sys_metrics:
                    if clg_sys_metrics[sort_col] is None:
                        has_all_sort_col = False
                        break
                if has_all_sort_col:
                    break

            if not has_all_sort_col:
                # If there's no common metric to sort them by, pick the first one.
                clg_id = all_clg_sys_metrics[0]['id']
            else:
                # Otherwise, find the primary system by sorting by the appropriate metric
                clg_id = sorted(all_clg_sys_metrics, key=lambda x: x[sort_col], reverse=True)[0]['id']

            clgsys = bldg.xpath('descendant::h:*[h:SystemIdentifier/@id=$clg_id]', namespaces=ns, clg_id=clg_id)[0]

    # Get the efficiency information about the cooling system
    clg_sys_el_name = clgsys.xpath('name()', namespaces=ns)
    if clg_sys_el_name == 'HeatPump':
        heat_pump_type = get_single_xpath_item(clgsys, 'h:HeatPumpType/text()')
        heat_pump_type = string.capwords(heat_pump_type)
        efficiency = get_single_xpath_item(clgsys, 'h:AnnualCoolEfficiency[1]/h:Value/text()')
        eff_units = get_single_xpath_item(clgsys, 'h:AnnualCoolEfficiency[1]/h:Units/text()')
        reso['Cooling'] = '{} Heat Pump, {} {}'.format(heat_pump_type, efficiency, eff_units)
    elif clg_sys_el_name == 'CoolingSystem':
        clg_sys_type = get_single_xpath_item(clgsys, 'h:CoolingSystemType/text()')
        clg_sys_type = string.capwords(clg_sys_type)
        efficiency = get_single_xpath_item(clgsys, 'h:AnnualCoolingEfficiency[1]/h:Value/text()', float)
        eff_units = get_single_xpath_item(clgsys, 'h:AnnualCoolingEfficiency[1]/h:Units/text()')
        reso['Cooling'] = '{}, {:.0f} {}'.format(clg_sys_type, efficiency, eff_units)
    else:
        assert False


    return reso


def main():
    parser = argparse.ArgumentParser('Convert HPXML to RESO-ish json')
    parser.add_argument('infile', type=argparse.FileType('rU'))
    parser.add_argument('-o', '--outfile', type=argparse.FileType('wb'), default=sys.stdout)
    parser.add_argument('--bldg_id', type=str, default=None)
    args = parser.parse_args()
    reso = hpxml2reso(args.infile, args.bldg_id)
    json.dump(reso, args.outfile, indent=4)


if __name__ == '__main__':
    main()
