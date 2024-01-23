# encoding=utf-8

#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2016 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
# Copyright (C) 2016 Marek Marczykowski-Górecki
#                              <marmarek@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""Qubes volume and block device management"""

import argparse
import itertools
import os
import sys

import qubesadmin
import qubesadmin.exc
import qubesadmin.tools
import qubesadmin.devices


def prepare_table(dev_list):
    """ Converts a list of :py:class:`qubes.devices.DeviceInfo` objects to a
    list of tuples for the :py:func:`qubes.tools.print_table`.

    If :program:`qvm-devices` is running in a TTY, it will omit duplicate
    data.

    :param iterable dev_list: List of :py:class:`qubes.devices.DeviceInfo`
        objects.
    :returns: list of tuples
    """
    output = []
    header = []
    if sys.stdout.isatty():
        header += [('BACKEND:DEVID', 'DESCRIPTION', 'USED BY')]  # NOQA

    for line in dev_list:
        output += [(
            line.ident,
            line.description,
            str(line.assignments),
        )]

    return header + sorted(output)


class Line(object):
    """Helper class to hold single device info for listing"""

    # pylint: disable=too-few-public-methods
    def __init__(self, device: qubesadmin.devices.DeviceInfo, attached_to=None):
        self.ident = "{!s}:{!s}".format(device.backend_domain, device.ident)
        self.description = device.description
        self.attached_to = attached_to if attached_to else ""
        self.frontends = []

    @property
    def assignments(self):
        """list of frontends the device is assigned to"""
        return ', '.join(self.frontends)


def list_devices(args):
    """ Called by the parser to execute the qubes-devices list
    subcommand. """
    app = args.app

    devices = set()
    try:
        if hasattr(args, 'domains') and args.domains:
            for domain in args.domains:
                for dev in domain.devices[args.devclass].get_assigned_devices():
                    devices.add(dev)
                for dev in domain.devices[args.devclass].get_attached_devices():
                    devices.add(dev)
                for dev in domain.devices[args.devclass].get_exposed_devices():
                    devices.add(dev)

        else:
            for domain in app.domains:
                try:
                    for dev in domain.devices[args.devclass].get_exposed_devices():
                        devices.add(dev)
                except qubesadmin.exc.QubesVMNotFoundError:
                    continue
    except qubesadmin.exc.QubesDaemonAccessError:
        raise qubesadmin.exc.QubesException(
            "Failed to list '%s' devices, this device type either "
            "does not exist or you do not have access to it.", args.devclass)

    result = {dev: Line(dev) for dev in devices}

    for dev in result:
        for domain in app.domains:
            if domain == dev.backend_domain:
                continue

            try:
                for assignment in (
                        domain.devices[args.devclass].get_dedicated_devices()):
                    if dev != assignment:
                        continue
                    if assignment.options:
                        result[dev].frontends.append('{!s} ({})'.format(
                            domain, ', '.join('{}={}'.format(key, value)
                                              for key, value in
                                              assignment.options.items())))
                    else:
                        result[dev].frontends.append(str(domain))
            except qubesadmin.exc.QubesVMNotFoundError:
                continue

    qubesadmin.tools.print_table(prepare_table(result.values()))


def attach_device(args):
    """ Called by the parser to execute the :program:`qvm-devices attach`
        subcommand.
    """
    vm = args.domains[0]
    device = args.device
    device_assignment = qubesadmin.devices.DeviceAssignment(
        device.backend_domain, device.ident)
    options = dict(opt.split('=', 1) for opt in args.option or [])
    if args.ro:
        options['read-only'] = 'yes'
    device_assignment.options = options
    vm.devices[args.devclass].attach(device_assignment)
    if args.required:
        device_assignment.required = args.required
        vm.devices[args.devclass].assign(device_assignment)


def detach_device(args):
    """ Called by the parser to execute the :program:`qvm-devices detach`
        subcommand.
    """
    vm = args.domains[0]
    if args.device:
        device = args.device
        device_assignment = qubesadmin.devices.DeviceAssignment(
            device.backend_domain, device.ident)
        vm.devices[args.devclass].detach(device_assignment)
    else:
        for device_assignment in (
                vm.devices[args.devclass].get_attached_devices()):
            vm.devices[args.devclass].detach(device_assignment)


def assign_device(args):
    """ Called by the parser to execute the :program:`qvm-devices assign`
        subcommand.
    """
    vm = args.domains[0]
    device = args.device
    device_assignment = qubesadmin.devices.DeviceAssignment(
        device.backend_domain, device.ident)
    options = dict(opt.split('=', 1) for opt in args.option or [])
    if args.ro:
        options['read-only'] = 'yes'
    device_assignment.attach_automatically = True
    device_assignment.required = args.required
    device_assignment.options = options
    vm.devices[args.devclass].assign(device_assignment)


def unassign_device(args):
    """ Called by the parser to execute the :program:`qvm-devices unassign`
        subcommand.
    """
    vm = args.domains[0]
    if args.device:
        device = args.device
        device_assignment = qubesadmin.devices.DeviceAssignment(
            device.backend_domain, device.ident)
        vm.devices[args.devclass].unassign(device_assignment)
    else:
        for device_assignment in (
                vm.devices[args.devclass].get_assigned_devices()):
            vm.devices[args.devclass].unassign(device_assignment)


def info_device(args):
    """ Called by the parser to execute the :program:`qvm-devices info`
        subcommand.
    """
    vm = args.domains[0]
    if args.device:
        device = args.device
        device_assignment = qubesadmin.devices.DeviceAssignment(
            device.backend_domain, device.ident)
        print("description:", device_assignment.device.description)
        print("data:", device_assignment.device.data)
    else:
        for device_assignment in (
                vm.devices[args.devclass].get_dedicated_devices()):
            print("device_assignment:", device_assignment)
            print("description:", device_assignment.device.description)
            print("data:", device_assignment.device.data)


def init_list_parser(sub_parsers):
    """ Configures the parser for the :program:`qvm-devices list` subcommand """
    # pylint: disable=protected-access
    list_parser = sub_parsers.add_parser('list', aliases=('ls', 'l'),
                                         help='list devices')

    vm_name_group = qubesadmin.tools.VmNameGroup(
        list_parser, required=False, vm_action=qubesadmin.tools.VmNameAction,
        help='list devices assigned to specific domain(s)')
    list_parser._mutually_exclusive_groups.append(vm_name_group)
    list_parser.set_defaults(func=list_devices)


class DeviceAction(qubesadmin.tools.QubesAction):
    """ Action for argument parser that gets the
        :py:class:``qubesadmin.device.Device`` from a
        BACKEND:DEVICE_ID string.
    """  # pylint: disable=too-few-public-methods

    def __init__(self, help='A backend & device id combination',
                 required=True, allow_unknown=False, **kwargs):
        # pylint: disable=redefined-builtin
        self.allow_unknown = allow_unknown
        super().__init__(help=help, required=required, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        """ Set ``namespace.device`` to ``values`` """
        setattr(namespace, self.dest, values)

    def parse_qubes_app(self, parser, namespace):
        app = namespace.app
        backend_device_id = getattr(namespace, self.dest)
        devclass = namespace.devclass
        if backend_device_id is None:
            return

        try:
            vmname, device_id = backend_device_id.split(':', 1)
            vm = None
            try:
                vm = app.domains[vmname]
            except KeyError:
                parser.error_runtime("no backend vm {!r}".format(vmname))

            try:
                dev = vm.devices[devclass][device_id]
                if not self.allow_unknown and \
                        isinstance(dev, qubesadmin.devices.UnknownDevice):
                    raise KeyError(device_id)
            except KeyError:
                parser.error_runtime(
                    "backend vm {!r} doesn't expose device {!r}".format(
                        vmname, device_id))
            device = qubesadmin.devices.Device(vm, device_id)
            setattr(namespace, self.dest, device)
        except ValueError:
            parser.error(
                'expected a backend vm & device id combination like foo:bar '
                'got %s' % backend_device_id)


def get_parser(device_class=None):
    """Create :py:class:`argparse.ArgumentParser` suitable for
    :program:`qvm-block`.
    """
    parser = qubesadmin.tools.QubesArgumentParser(description=__doc__)
    parser.register('action', 'parsers',
                    qubesadmin.tools.AliasedSubParsersAction)
    parser.allow_abbrev = False
    if device_class:
        parser.add_argument('devclass', const=device_class,
                            action='store_const',
                            help=argparse.SUPPRESS)
    else:
        parser.add_argument('devclass', metavar='DEVICE_CLASS', action='store',
                            help="Device class to manage ('pci', 'usb', etc)")

    # default action
    parser.set_defaults(func=list_devices)

    sub_parsers = parser.add_subparsers(
        title='commands',
        description="For more information see qvm-device command -h",
        dest='command')
    init_list_parser(sub_parsers)
    attach_parser = sub_parsers.add_parser(
        'attach', help="Attach device to domain", aliases=('at', 'a'))
    detach_parser = sub_parsers.add_parser(
        "detach", help="Detach device from domain", aliases=('d', 'dt'))
    assign_parser = sub_parsers.add_parser(
        'assign',
        help="Assign device to domain or edit existing assignment",
        aliases=('s',))
    unassign_parser = sub_parsers.add_parser(
        "unassign",
        help="Remove assignment of device from domain",
        aliases=('u',))
    info_parser = sub_parsers.add_parser(
        "info", help="Show info about device from domain", aliases=('i',))

    attach_parser.add_argument('VMNAME', nargs=1,
                               action=qubesadmin.tools.VmNameAction)
    detach_parser.add_argument('VMNAME', nargs=1,
                               action=qubesadmin.tools.VmNameAction)
    assign_parser.add_argument('VMNAME', nargs=1,
                               action=qubesadmin.tools.VmNameAction)
    unassign_parser.add_argument('VMNAME', nargs=1,
                                 action=qubesadmin.tools.VmNameAction)
    info_parser.add_argument('VMNAME', nargs=1,
                             action=qubesadmin.tools.VmNameAction)

    attach_parser.add_argument(metavar='BACKEND:DEVICE_ID',
                               dest='device',
                               action=DeviceAction)
    detach_parser.add_argument(metavar='BACKEND:DEVICE_ID',
                               dest='device',
                               nargs=argparse.OPTIONAL,
                               action=DeviceAction, allow_unknown=True)
    assign_parser.add_argument(metavar='BACKEND:DEVICE_ID',
                               dest='device',
                               action=DeviceAction)
    unassign_parser.add_argument(metavar='BACKEND:DEVICE_ID',
                                 dest='device',
                                 action=DeviceAction, allow_unknown=True)
    info_parser.add_argument(metavar='BACKEND:DEVICE_ID',
                             dest='device',
                             nargs=argparse.OPTIONAL,
                             action=DeviceAction, allow_unknown=True)

    attach_parser.add_argument('--option', '-o', action='append',
                               help="Set option for the device in opt=value "
                                    "form (can be specified "
                                    "multiple times), see man qvm-device for "
                                    "details")
    assign_parser.add_argument('--option', '-o', action='append',
                               help="Set option for the device in opt=value "
                                    "form (can be specified "
                                    "multiple times), see man qvm-device for "
                                    "details")  # TODO
    attach_parser.add_argument('--ro', action='store_true', default=False,
                               help="Attach device read-only (alias for "
                                    "read-only=yes option, "
                                    "takes precedence)")
    assign_parser.add_argument('--ro', action='store_true', default=False,
                               help="Attach device read-only (alias for "
                                    "read-only=yes option, "
                                    "takes precedence)")  # TODO
    attach_parser.add_argument('--persistent', '-p',
                               dest='required',
                               action='store_true',
                               default=False,
                               help="Alias to `assign --required` for backward "
                                    "compatibility")
    assign_parser.add_argument('--required', '-r',
                               dest='required',
                               action='store_true',
                               default=False,
                               help="Mark device as required so it will "
                                    "be required to the qube's startup and then"
                                    " automatically attached)")

    attach_parser.set_defaults(func=attach_device)
    detach_parser.set_defaults(func=detach_device)
    assign_parser.set_defaults(func=assign_device)
    unassign_parser.set_defaults(func=unassign_device)
    info_parser.set_defaults(func=info_device)

    parser.add_argument('--list-device-classes', action='store_true',
                        default=False)

    return parser


def main(args=None, app=None):
    """Main routine of :program:`qvm-block`."""
    basename = os.path.basename(sys.argv[0])
    devclass = None
    if basename.startswith('qvm-') and basename != 'qvm-device':
        devclass = basename[4:]

    # Special treatment for '--list-device-classes' (alias --list-classes)
    curr_action = sys.argv[1:]
    if set(curr_action).intersection(
            {'--list-device-classes', '--list-classes'}):
        print('\n'.join(qubesadmin.Qubes().list_deviceclass()))
        return 0

    parser = get_parser(devclass)
    args = parser.parse_args(args, app=app)

    try:
        args.func(args)
    except qubesadmin.exc.QubesException as e:
        parser.print_error(str(e))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
