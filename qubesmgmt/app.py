# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2017 Marek Marczykowski-Górecki
#                               <marmarek@invisiblethingslab.com>
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
# with this program; if not, see <http://www.gnu.org/licenses/>.

import socket

import subprocess

import qubesmgmt
import qubesmgmt.vm
import qubesmgmt.exc

QUBESD_SOCK = '/var/run/qubesd.sock'
BUF_SIZE = 4096

class VMCollection(object):
    def __init__(self, app):
        self.app = app
        self._vm_list = None

    def refresh_cache(self, force=False):
        if not force and self._vm_list is not None:
            return
        vm_list_data = self.app._do_qubesd_call(
            'dom0',
            'mgmt.vm.List'
        )
        new_vm_list = {}
        # FIXME: this will probably change
        for vm_data in vm_list_data.splitlines():
            vm_name, props = vm_data.split(b' ', 1)
            props = props.split(b' ')
            new_vm_list[vm_name] = dict(
                [vm_prop.split(b'=', 1) for vm_prop in props])

        self._vm_list = new_vm_list

    def __getitem__(self, item):
        if item not in self:
            raise KeyError(item)
        return qubesmgmt.vm.QubesVM(
            self.app, item, self._vm_list[item]['class'])

    def __contains__(self, item):
        self.refresh_cache()
        return item in self._vm_list

    def __iter__(self):
        self.refresh_cache()
        for vm in self._vm_list:
            yield self[vm]

    def keys(self):
        self.refresh_cache()
        return self._vm_list.keys()


class QubesBase(qubesmgmt.PropertyHolder):
    '''Main Qubes application'''

    #: domains (VMs) collection
    domains = None

    def __init__(self):
        super(QubesBase, self).__init__(self, 'mgmt.global.', 'dom0')
        self.domains = VMCollection(self)


class QubesLocal(QubesBase):
    def _do_qubesd_call(self, dest, method, arg=None, payload=None):
        try:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_socket.connect(QUBESD_SOCK)
        except IOError:
            # TODO:
            raise

        # src, method, dest, arg
        for call_arg in ('dom0', method, dest, arg):
            client_socket.sendall(call_arg.encode('ascii'))
            client_socket.sendall(b'\0')
        if payload is not None:
            client_socket.sendall(payload)

        return_data = b''.join(iter(client_socket.recv(BUF_SIZE), b''))
        return self._parse_qubesd_response(return_data)


class QubesRemote(QubesBase):
    def _do_qubesd_call(self, dest, method, arg=None, payload=None):
        service_name = method
        if arg is not None:
            service_name += '+' + arg
        p = subprocess.Popen(['qrexec-client-vm', dest, service_name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (stdout, stderr) = p.communicate(payload)
        if p.returncode != 0:
            # TODO: use dedicated exception
            raise qubesmgmt.exc.QubesException('Service call error: %s',
                stderr.decode())

        return self._parse_qubesd_response(stdout)