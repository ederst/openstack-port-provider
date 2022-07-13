# OpenStack Port Provider

The OpenStack Port Provider is a simple program which runs on a server in OpenStack and attaches ports for every subnet the provider should manage.

## Limitations

* Creates ports with one fixed IP/subnet only
* Uses the first IP it finds on a port only to create the networking config
