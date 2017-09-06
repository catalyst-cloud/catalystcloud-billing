# Separate Billing

Get separate billing based on the prefix on resource so that the Catalyst Cloud
customer can easily charge their customer based on usage.

> Note: This script is just a reference about how to consume Catalyst Cloud
billing API to get a separate billing based on the latest invoice. But it's
really easy to change the code to meet the other requirements.

## How to use

To use this script please set appropriate prefix for your resource name.

### Preparing your local environment

Create a python virtual environment and install the libraries required by the
command line tool in it.

``` bash
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Get billing based on the prefix of customer

Source an openrc file with your credentials to wccess the Catalyst Cloud, as
described at
http://docs.catalystcloud.io/getting-started/cli.html#source-an-openstack-rc-file.

> Note: if you do not source an openrc file, you will need to pass the
> authentication information to the command line tool when running it. See
> ./separate-billing.py help for more infromation.

Make sure your python virtual environment is activated (`source
venv/bin/activate`).

Sample usage:

``` bash
./separate-billing.py show --prefix customer-wcc
```

The response will be like:

```
+-------------------------------+--------+----------+---------+-------+
| resource_name                 | rate   | quantity | unit    | cost  |
+-------------------------------+--------+----------+---------+-------+
| customer-wcc-ipsec-router-fdc | 0.017  | 697.0    | Hour(s) | 11.85 |
| customer-wcc-ipsec-router-gdc | 0.017  | 697.0    | Hour(s) | 11.85 |
| customer-wcc-fdc-vpnservice   | 0.017  | 697.0    | Hour(s) | 11.85 |
| customer-wcc-gdc-vpnservice   | 0.017  | 697.0    | Hour(s) | 11.85 |
| customer-wcc-fdc              | 0.0164 | 697.0    | Hour(s) | 11.43 |
| customer-wcc                  | 0.0164 | 697.0    | Hour(s) | 11.43 |
| customer-wcc-gdc              | 0.0164 | 697.0    | Hour(s) | 11.43 |
+-------------------------------+--------+----------+---------+-------+
Total cost of customer [customer-wcc] for the month of [2017-07-31] is : $81.69
```

The parameter **prefix** is used to filter the invoice to get the separate
billing for different customers.

> Note: To view the full invoice, just issue command as below:
``` bash
./separate-billing.py show --prefix ''
```

