"""
    This Source Code Form is subject to the terms of the Mozilla Public 
    License, v. 2.0. If a copy of the MPL was not distributed with this 
    file, You can obtain one at http://mozilla.org/MPL/2.0/.

    Software distributed under the License is distributed on an "AS IS"
    basis, WITHOUT WARRANTY OF ANY KIND, either express or implied. See the
    License for the specific language governing rights and limitations
    under the License.

    The Original Code is FreePyBX/VoiceWARE.

    The Initial Developer of the Original Code is Noel Morgan,
    Copyright (c) 2011-2012 VoiceWARE Communications, Inc. All Rights Reserved.

    http://www.vwci.com/

    You may not remove or alter the substance of any license notices (including
    copyright notices, patent notices, disclaimers of warranty, or limitations
    of liability) contained within the Source Code Form of the Covered Software,
    except that You may alter any license notices to the extent required to
    remedy known factual inaccuracies.
"""
import os

import formencode
import shutil
import urllib
import logging
import cgitb; cgitb.enable()

from pylons import config
from pylons import request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect
from pylons.decorators.rest import restrict
from pylons.decorators import validate, jsonify

import formencode
from formencode import validators

from freepybx.lib.base import BaseController, render
from freepybx.model import meta
from freepybx.model.meta import *
from freepybx.model.meta import Session as db
from freepybx.lib.auth import *
from freepybx.lib.forms import *
from freepybx.lib.util import *
from freepybx.lib.util import PbxError, DataInputError, PbxEncoder
from freepybx.lib.validators import *

from genshi import HTML
from decorator import decorator

import simplejson as json
from simplejson import loads, dumps


from sqlalchemy import Date, cast, desc, asc
from sqlalchemy.orm import join

# Import Auth decorators etc.
logged_in = IsLoggedIn()
super_user = IsSuperUser()
credentials = HasCredential(object)
log = logging.getLogger(__name__)

fs_vm_dir = config['app_conf']['fs_vm_dir']
fs_profile = config['app_conf']['fs_profile']


class CredentialError(Exception):
    message=""
    def __init__(self, message=None):
        Exception.__init__(self, message or self.message)

class AdminController(BaseController):
    """Admin controller:

    This admin module is reponsible for the majority of the applications
    adminstrative functionality and is mainly for restricted use.

    """
    @authorize(super_user)
    def index(self, **kw):
        c.sid = session.id
        c.my_name = session["name"]
        c.profiles = PbxProfile.query.all()
        return render('admin/admin.html')

    def logout(self, **kw):
        try:
            if 'user' in session:
                session.invalidate()
                del session['user']
        except:
            pass
        return self.login()

    def login(self, **kw):
        try:
            if 'user' in session:
                session.invalidate()
                del session['user']
        except:
            pass
            session.invalidate()
        return render('admin/login.html')

    @restrict("POST")
    def auth_admin(self, **kw):
        schema = LoginForm()
        try:
            form_result = schema.to_python(request.params)
            username = form_result.get("username")
            password = form_result.get("password")
        except:
            return AuthenticationError("Auth error...")

        if not authenticate_admin(username, password):
            return self.login()
        else:
            session.save()
        c.sid = session.id
        c.my_name = session["name"]
        c.profiles = PbxProfile.query.all()
        return render('admin/admin.html')

    @authorize(super_user)
    def main(self, **kw):
        c.sid = session.id
        c.my_name = session["name"]
        c.profiles = PbxProfile.query.all()

        return render('admin/admin.html')

    @authorize(super_user)
    def users(self):
        items=[]
        for row in User.query.order_by(asc(User.id)).all():
            exts = []
            for ext in PbxEndpoint.query.filter(PbxEndpoint.user_id==row.id).filter_by(user_context=row.context).all():
                exts.append(ext.auth_id)
            if not len(exts) > 0:
                extension = "No Extension"
            else:
                extension = ", ".join(exts)
            items.append({'id': row.id, 'extension': extension, 'username': row.username, 'password': row.password, 'first_name': row.first_name,
                          'name': row.first_name +' '+row.last_name, 'context': row.context,
                          'last_name': row.last_name, 'address': row.address, 'address_2': row.address_2, 'city': row.city, 'state': row.state, 'zip': row.zip,
                          'tel': row.tel, 'mobile': row.mobile, 'notes': row.notes, 'created': row.created.strftime("%m/%d/%Y %I:%M:%S %p"), 'updated': row.updated.strftime("%m/%d/%Y %I:%M:%S %p"), 'active': row.active,
                          'group_id': row.group_id, 'last_login': row.last_login.strftime("%m/%d/%Y %I:%M:%S %p"), 'remote_addr': row.remote_addr, 'session_id': row.session_id, 'customer_id': row.customer_id})

        db.remove()

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)


    @authorize(super_user)
    def customers(self):
        items=[]
        for row in Customer.query.all():
            items.append({'id': row.id, 'name': row.name, 'active': row.active, 'tel': row.tel})

        out = dict({'identifier': 'name', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @jsonify
    @authorize(super_user)
    def customer_store(self):
        items=[]
        for row in Customer.query.all():
            items.append({'id': row.id, 'name': row.name, 'active': row.active, 'tel': row.tel})

        return {'identifier': 'id', 'label': 'name', 'items': items}

    @jsonify
    @authorize(super_user)
    def customer_by_id(self, id, **kw):
        items=[]

        try:
            customer = Customer.query.filter(Customer.id==id).first()

            if customer is None:
                raise Exception("No customer with that ID.")

            profile = PbxProfile.query.filter_by(id=customer.pbx_profile_id).first()

            items.append({'id': customer.id, 'name': customer.name,  'profile': profile.name, 'email': customer.email,
                          'address': customer.address, 'address_2': customer.address_2,
                          'city': customer.city, 'state': customer.state, 'zip': customer.zip, 'default_gateway': customer.default_gateway,
                          'tel': customer.tel, 'url': customer.url, 'active': customer.active, 'context': customer.context,
                          'has_crm': customer.has_crm, 'has_call_center': customer.has_call_center,
                          'contact_name': customer.contact_name, 'contact_phone': customer.contact_phone, 'contact_mobile': customer.contact_mobile,
                          'contact_title': customer.contact_title, 'contact_email': customer.contact_email, 'notes': customer.notes,
                          'pbx_profile_id': customer.pbx_profile_id, 'inbound_channel_limit': customer.inbound_channel_limit,
                          'outbound_channel_limit': customer.outbound_channel_limit,
                          'hard_channel_limit': customer.hard_channel_limit, 'channel_audio': customer.channel_audio})

            return {'identifier': 'id', 'label': 'name', 'items': items}

        except Exception, e:
            return {'identifier': 'id', 'label': 'name', 'items': [], 'error': str(e)}

    @authorize(super_user)
    def update_customer_grid(self, **kw):

        try:
            w = loads(urllib.unquote_plus(request.params.get("data")))

            for i in w['modified']:
                co = Customer.query.filter_by(id=i['id']).first()
                co.active = i['active']

                db.commit()
                db.flush()
                db.remove()

        except DataInputError, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully updated Customer."

    @authorize(super_user)
    def add_customer(self):
        schema = CustomerForm()
        try:
            form_result = schema.to_python(request.params)
            customer = Customer()
            customer.name = form_result.get('name')
            customer.tel = form_result.get('cust_tel')
            customer.address = form_result.get('address')
            customer.address_2 = form_result.get('address_2')
            customer.city = form_result.get('city')
            customer.state = form_result.get('state')
            customer.zip = form_result.get('zip')
            customer.url = form_result.get('url')
            customer.context = form_result.get('context')
            customer.email = form_result.get('contact_email')
            customer.contact_name = form_result.get('contact_name')
            customer.contact_phone = form_result.get('contact_phone')
            customer.contact_mobile = form_result.get('contact_mobile')
            customer.contact_title = form_result.get('contact_title')
            customer.contact_email = form_result.get('contact_email')
            customer.active = True if form_result.get('active')=="true" else False
            customer.has_crm = True if form_result.get('has_crm')=="true" else False
            customer.has_call_center = True if form_result.get('has_call_center')=="true" else False
            customer.default_gateway = form_result.get('default_gateway')
            customer.pbx_profile_id = form_result.get('pbx_profile_id')
            customer.inbound_channel_limit = form_result.get('inbound_channel_limit')
            customer.channel_audio = form_result.get('channel_audio')

            try:
                os.makedirs(fs_vm_dir+str(customer.context)+'/recordings')
                os.makedirs(fs_vm_dir+str(customer.context)+'/system/recordings')
                os.makedirs(fs_vm_dir+str(customer.context)+'/queue-recordings')
                os.makedirs(fs_vm_dir+str(customer.context)+'/extension-recordings')
                os.makedirs(fs_vm_dir+str(customer.context)+'/faxes')
            except:
                pass

            db.add(customer)
            db.commit()

            context = PbxContext(customer.id, form_result.get('domain'), form_result.get('context'), form_result.get('default_gateway'),
                customer.profile, customer.name, form_result.get('did', customer.name, customer.tel))

            db.add(context)
            customer.pbx_contexts.append(context)

            db.add(PbxDid(form_result.get('cust_add_did'), customer.id,
                form_result.get('context'), form_result.get('domain'), form_result.get('t38', False), form_result.get('e911', False),
                form_result.get('cnam', False), True))

            db.commit()
            db.flush()
            db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully created customer."

    @authorize(super_user)
    def customers_id(self):
        items=[]
        for row in Customer.query.all():
            items.append({'id': row.id, 'name': row.name, 'active': row.active, 'tel': row.tel})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def edit_customer(self):
        schema = CustomerEditForm()
        try:
            form_result = schema.to_python(request.params)
            customer = Customer.query.filter_by(id=form_result.get('edit_customer_id')).first()
            customer.name = form_result.get('customer_name')
            customer.tel = form_result.get('cust_tel')
            customer.address = form_result.get('address')
            customer.address_2 = form_result.get('address_2')
            customer.city = form_result.get('city')
            customer.state = form_result.get('state')
            customer.zip = form_result.get('zip')
            customer.url = form_result.get('url')
            customer.email = form_result.get('contact_email')
            customer.contact_name = form_result.get('contact_name')
            customer.contact_phone = form_result.get('contact_phone')
            customer.contact_mobile = form_result.get('contact_mobile')
            customer.contact_title = form_result.get('contact_title')
            customer.contact_email = form_result.get('contact_email')
            customer.active = True if form_result.get('active')=="true" else False
            customer.has_crm = True if form_result.get('find_me')=="true" else False
            customer.has_call_center = True if form_result.get('has_call_center')=="true" else False
            customer.default_gateway = form_result.get('default_gateway')
            customer.pbx_profile_id = form_result.get('pbx_profile_id')
            customer.hard_channel_limit = form_result.get('hard_channel_limit')
            customer.inbound_channel_limit = form_result.get('inbound_channel_limit')
            customer.outbound_channel_limit = form_result.get('outbound_channel_limit')
            customer.channel_audio = form_result.get('channel_audio')

            db.flush()
            db.commit()
            db.remove()

            return "Successfully edited customer."

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

    @authorize(super_user)
    def update_customer_grid(self, **kw):

        try:
            w = loads(urllib.unquote_plus(request.params.get("data")))

            for i in w['modified']:
                co = Customer.query.filter_by(id=i['id']).first()
                customer.active = i['active']

                db.commit()
                db.flush()
                db.remove()

        except DataInputError, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully updated Customer."

    @authorize(super_user)
    def del_customer(self, **kw):

        cust = Customer.query.filter_by(id=request.params.get("id")).first()

        try:
            if cust.context:
                delete_customer(cust.context)
        except Exception, e:
            return 'Error: %s' % e

        return "Successfully deleted Customer."

    @authorize(logged_in)
    def user_groups(self, **kw):
        items=[]
        for row in Group.query.all():
            items.append({'id': row.id, 'name': row.name, 'description': row.description})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)


    @authorize(super_user)
    def profiles(self, **kw):
        items=[]
        for row in  PbxProfile.query.all():
            items.append({'name': row.name, 'ext_rtp_ip': row.ext_rtp_ip, 'ext_sip_ip': row.ext_sip_ip, 'sip_port': row.sip_port,
                          'accept_blind_reg': row.accept_blind_reg, 'auth_calls': row.auth_calls, 'email_domain': row.email_domain})

        out = dict({'identifier': 'name', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def get_profile_by_id(self, id, **kw):
        items=[]
        row = PbxProfile.query.filter_by(id=id).first()
        items.append({'id': row.id, 'name': row.name, 'odbc_credentials': row.odbc_credentials, 'manage_presence': row.manage_presence, 'presence_hosts': row.presence_hosts,
                      'send_presence_on_register': row.send_presence_on_register, 'delete_subs_on_register': row.delete_subs_on_register, 'caller_id_type': row.caller_id_type,
                      'auto_jitterbuffer_msec': row.auto_jitterbuffer_msec, 'dialplan': row.dialplan, 'ext_rtp_ip': row.ext_rtp_ip, 'ext_sip_ip': row.ext_sip_ip, 'rtp_ip': row.rtp_ip,
                      'sip_ip': row.sip_ip, 'sip_port': row.sip_port, 'nonce_ttl': row.nonce_ttl, 'sql_in_transactions': row.sql_in_transactions, 'use_rtp_timer': row.use_rtp_timer,
                      'codec_prefs': row.codec_prefs, 'inbound_codec_negotiation': row.inbound_codec_negotiation, 'rtp_timeout_sec': row.rtp_timeout_sec, 'rfc2833_pt': row.rfc2833_pt,
                      'dtmf_duration': row.dtmf_duration, 'dtmf_type': row.dtmf_type, 'session_timeout': row.session_timeout, 'multiple_registrations': row.multiple_registrations,
                      'vm_from_email': row.vm_from_email, 'accept_blind_reg': row.accept_blind_reg, 'auth_calls': row.auth_calls, 'email_domain': row.email_domain,
                      'rtp_timer_name': row.rtp_timer_name, 'presence_db_name': row.presence_db_name, 'codec_ms': row.codec_ms, 'disable_register': row.disable_register,
                      'log_auth_failures': row.log_auth_failures, 'auth_all_packets':row.auth_all_packets, 'minimum_session_expires': row.minimum_session_expires})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def profiles_id(self, **kw):
        items=[]
        for row in  PbxProfile.query.all():
            items.append({'id': row.id, 'name': row.name, 'ext_rtp_ip': row.ext_rtp_ip, 'ext_sip_ip': row.ext_sip_ip, 'sip_port': row.sip_port})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def profiles_ids(self, **kw):
        items=[]
        for row in  PbxProfile.query.all():
            items.append({'id': row.id, 'name': row.name, 'ext_rtp_ip': row.ext_rtp_ip, 'ext_sip_ip': row.ext_sip_ip, 'sip_port': row.sip_port})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def add_profile(self):

        schema = ProfileForm()

        try:
            form_result = schema.to_python(request.params)
            sp = PbxProfile()
            sp.name = form_result.get('name')
            sp.odbc_credentials = form_result.get('odbc_credentials')
            sp.manage_presence = True if form_result.get('manage_presence')=="true" else False
            sp.presence_db_name = form_result.get('dbname', None)
            sp.presence_hosts = form_result.get('presence_hosts', None)
            sp.send_presence_on_register = True if form_result.get('send_presence_on_register')=="true" else False
            sp.delete_subs_on_register = True if form_result.get('delete_subs_on_register')=="true" else False
            sp.caller_id_type = form_result.get('caller_id_type', u'rpid')
            sp.auto_jitterbuffer_msec = form_result.get('auto_jitterbuffer_msec', 120)
            sp.dialplan = form_result.get('dialplan', u'XML,enum')
            sp.ext_rtp_ip = form_result.get('ext_rtp_ip', None)
            sp.ext_sip_ip = form_result.get('ext_sip_ip', None)
            sp.rtp_ip = form_result.get('rtp_ip', None)
            sp.sip_ip = form_result.get('sip_ip', None)
            sp.sip_port = form_result.get('sip_port', 5060)
            sp.nonce_ttl = form_result.get('nonce_ttl', 60)
            sp.sql_in_transactions = True if form_result.get('sql_in_transactions')=="true" else False
            sp.use_rtp_timer = True if form_result.get('use_rtp_timer')=="true" else False
            sp.rtp_timer_name =  form_result.get('rtp_timer_name', u'soft')
            sp.codec_prefs = form_result.get('codec_prefs', u'PCMU,PCMA,G722,G726,H264,H263')
            sp.inbound_codec_negotiation = form_result.get('inbound_codec_negotiation', u'generous')
            sp.codec_ms = form_result.get('codec_ms', 20)
            sp.rtp_timeout_sec = form_result.get('rtp_timeout_sec', 300)
            sp.rtp_hold_timeout_sec = form_result.get('rtp_hold_timeout_sec', 1800)
            sp.rfc2833_pt = form_result.get('rfc2833_pt', 101)
            sp.dtmf_duration = form_result.get('dtmf_duration', 100)
            sp.dtmf_type = form_result.get('dtmf_type', u'rfc2833')
            sp.session_timeout = form_result.get('session_timeout', 1800)
            sp.multiple_registrations = form_result.get('multiple_registrations', u'contact')
            sp.vm_from_email = form_result.get('vm_from_email', u'voicemail@freeswitch')
            sp.accept_blind_reg = True if form_result.get('accept_blind_reg')=="true" else False
            sp.auth_calls = True if form_result.get('auth_calls')=="true" else False
            sp.email_domain = form_result.get('email_domain', u'freeswitch.org')
            sp.auth_all_packets = True if form_result.get('auth_all_packets')=="true" else False
            sp.log_auth_failures = True if form_result.get('log_auth_failures')=="true" else False
            sp.disable_register = True if form_result.get('disable_register')=="true" else False
            sp.minimum_session_expires = form_result.get('minimum_session_expires', 120)

            db.add(sp)
            db.commit()
            db.flush()

        except validators.Invalid, error:
            db.remove()
            return 'Validation Error: %s' % error

        db.remove()

        return "Successfully added profile."

    @authorize(super_user)
    def edit_profile(self):

        schema = ProfileEditForm()

        try:
            form_result = schema.to_python(request.params)
            sp = PbxProfile.query.filter_by(id=form_result.get('id',0)).first()
            sp.odbc_credentials = form_result.get('odbc_credentials')
            sp.manage_presence = True if form_result.get('manage_presence')=="true" else False
            sp.presence_db_name = form_result.get('dbname', None)
            sp.presence_hosts = form_result.get('presence_hosts', None)
            sp.send_presence_on_register = True if form_result.get('send_presence_on_register')=="true" else False
            sp.delete_subs_on_register = True if form_result.get('delete_subs_on_register')=="true" else False
            sp.caller_id_type = form_result.get('caller_id_type', u'rpid')
            sp.auto_jitterbuffer_msec = form_result.get('auto_jitterbuffer_msec', 120)
            sp.dialplan = form_result.get('dialplan', u'XML,enum')
            sp.ext_rtp_ip = form_result.get('ext_rtp_ip', None)
            sp.ext_sip_ip = form_result.get('ext_sip_ip', None)
            sp.rtp_ip = form_result.get('rtp_ip', None)
            sp.sip_ip = form_result.get('sip_ip', None)
            sp.sip_port = form_result.get('sip_port', 5060)
            sp.nonce_ttl = form_result.get('nonce_ttl', 60)
            sp.sql_in_transactions = True if form_result.get('sql_in_transactions')=="true" else False
            sp.use_rtp_timer = True if form_result.get('use_rtp_timer')=="true" else False
            sp.rtp_timer_name =  form_result.get('rtp_timer_name', u'soft')
            sp.codec_prefs = form_result.get('codec_prefs', u'PCMU,PCMA,G722,G726,H264,H263')
            sp.inbound_codec_negotiation = form_result.get('inbound_codec_negotiation', u'generous')
            sp.codec_ms = form_result.get('codec_ms', 20)
            sp.rtp_timeout_sec = form_result.get('rtp_timeout_sec', 300)
            sp.rtp_hold_timeout_sec = form_result.get('rtp_hold_timeout_sec', 1800)
            sp.rfc2833_pt = form_result.get('rfc2833_pt', 101)
            sp.dtmf_duration = form_result.get('dtmf_duration', 100)
            sp.dtmf_type = form_result.get('dtmf_type', u'rfc2833')
            sp.session_timeout = form_result.get('session_timeout', 1800)
            sp.multiple_registrations = form_result.get('multiple_registrations', u'contact')
            sp.vm_from_email = form_result.get('vm_from_email', u'voicemail@freeswitch')
            sp.accept_blind_reg = True if form_result.get('accept_blind_reg')=="true" else False
            sp.auth_calls = True if form_result.get('auth_calls')=="true" else False
            sp.email_domain = form_result.get('email_domain', u'freeswitch.org')
            sp.auth_all_packets = True if form_result.get('auth_all_packets')=="true" else False
            sp.log_auth_failures = True if form_result.get('log_auth_failures')=="true" else False
            sp.disable_register = True if form_result.get('disable_register')=="true" else False
            sp.minimum_session_expires = form_result.get('minimum_session_expires', 120)

            db.add(sp)
            db.commit()
            db.flush()

        except validators.Invalid, error:
            db.remove()
            return 'Validation Error: %s' % error

        db.remove()
        return "Successfully updated profile."

    @authorize(super_user)
    def gateways(self, **kw):
        items=[]
        for row in PbxGateway.query.all():
            profile = PbxProfile.query.filter_by(id=row.pbx_profile_id).first()
            items.append({'id': row.id,'name': row.name, 'proxy': row.proxy, 'mask': row.mask, 'register': row.register,
                          'profile': profile.name})

        out = dict({'identifier': 'name', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def gateway_store(self, **kw):
        items=[]
        for row in PbxGateway.query.all():
            profile = PbxProfile.query.filter_by(id=row.pbx_profile_id).first()
            items.append({'id': row.id,'name': row.name, 'proxy': row.proxy, 'mask': row.mask, 'register': row.register,
                          'profile': profile.name})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def gateway_by_id(self, id, **kw):
        items=[]
        row = PbxGateway.query.filter(PbxGateway.id==id).first()
        profile = PbxProfile.query.filter_by(id=row.pbx_profile_id).first()
        items.append({'id': row.id, 'name': row.name, 'pbx_profile_id': row.pbx_profile_id, 'username': row.username, 'password': row.password,
                      'proxy': row.proxy, 'register': row.register, 'register_transport': row.register_transport, 'reg_id': row.reg_id, 'rfc5626': row.rfc5626,
                      'extension': row.extension, 'realm': row.realm, 'from_domain': row.from_domain, 'expire_seconds': row.expire_seconds, 'retry_seconds': row.retry_seconds,
                      'ping': row.ping, 'context': row.context, 'caller_id_in_from': row.caller_id_in_from,
                      'mask': row.mask, 'contact_params': row.contact_params, })

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def add_gateway(self, **kw):
        schema = GatewayForm()

        try:
            form_result = schema.to_python(request.params)
            gw = PbxGateway()

            gw.name = form_result.get('name')
            gw.pbx_profile_id = form_result.get('pbx_profile_id')
            gw.username = form_result.get('gateway_username')
            gw.password = form_result.get('password')
            gw.realm = form_result.get('realm')
            gw.proxy = form_result.get('proxy')
            gw.register = form_result.get('register', False)
            gw.register_transport = form_result.get('register_transport')
            gw.extension = form_result.get('extension')
            gw.from_domain = form_result.get('from_domain')
            gw.expire_seconds = form_result.get('expire_seconds')
            gw.retry_seconds = form_result.get('retry_seconds')
            gw.ping = form_result.get('ping')
            gw.context = form_result.get('context')
            gw.caller_id_in_from = form_result.get('caller_id_in_from')
            gw.mask =  form_result.get('mask')
            gw.rfc5626 = form_result.get('rfc5626', True)
            gw.reg_id = form_result.get('reg_id', 1)
            gw.contact_params = form_result.get('contact_params', u'tport=tcp')

            db.add(gw)
            db.commit()
            db.flush()
            db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully added gateway."

    @authorize(super_user)
    def edit_gateway(self):

        schema = GatewayEditForm()

        try:
            form_result = schema.to_python(request.params)

            gw = PbxGateway.query.filter(PbxGateway.id==form_result.get('gateway_id')).first()
            gw.pbx_profile_id = form_result.get('pbx_profile_id')
            gw.username = form_result.get('gateway_username')
            gw.password = form_result.get('password')
            gw.proxy = form_result.get('proxy')
            gw.register = form_result.get('register', False)
            gw.register_transport = form_result.get('register_transport')
            gw.extension = form_result.get('extension')
            gw.realm = form_result.get('realm')
            gw.from_domain = form_result.get('from_domain')
            gw.expire_seconds = form_result.get('expire_seconds')
            gw.retry_seconds = form_result.get('retry_seconds')
            gw.ping = form_result.get('ping')
            gw.context = form_result.get('context')
            gw.caller_id_in_from = form_result.get('caller_id_in_from')
            gw.mask =  form_result.get('mask')
            gw.rfc5626 = form_result.get('rfc5626', True)
            gw.reg_id = form_result.get('reg_id', 1)
            gw.contact_params = form_result.get('contact_params', u'tport=tcp')

            db.add(gw)
            db.commit()
            db.flush()
            db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully edited gateway."

    @authorize(super_user)
    def update_gw_grid(self, **kw):

        try:
            w = loads(urllib.unquote_plus(request.params.get("data")))

            for i in w['modified']:
                gw = PbxGateway.query.filter_by(id=i['id']).first()
                pro = PbxProfile.query.filter_by(name=i['profile']).first()
                gw.register = i['register']
                gw.pbx_profile_id = pro.id

                db.commit()
                db.flush()
                db.remove()

        except DataInputError, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully updated Gateway."

    @authorize(super_user)
    def outbound_routes(self, **kw):
        items=[]
        for row in db.query(PbxOutboundRoute.id, PbxOutboundRoute.name, PbxOutboundRoute.customer_id, PbxOutboundRoute.gateway_id, PbxOutboundRoute.pattern,
                            Customer.name).filter(PbxOutboundRoute.customer_id==Customer.id).all():
            items.append({'id': row[0],'name': row[1], 'customer_id': row[2],
                          'gateway_id': row[3], 'pattern': row[4], 'customer_name': row[5],
                          'gateway': get_gateway(row[3])})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def outroute_by_id(self, id, **kw):
        items=[]
        for row in db.query(PbxOutboundRoute.id, PbxOutboundRoute.name, PbxOutboundRoute.customer_id, PbxOutboundRoute.gateway_id, PbxOutboundRoute.pattern,
            Customer.name).filter(PbxOutboundRoute.customer_id==Customer.id).filter(PbxOutboundRoute.id==id).all():
            items.append({'id': row[0],'name': row[1], 'customer_id': row[2],
                          'gateway_id': row[3], 'pattern': row[4], 'customer_name': row[5],
                          'gateway': get_gateway(row[3])})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def add_outroute(self, **kw):
        schema = OutboundRouteForm()

        try:
            form_result = schema.to_python(request.params)
            por = PbxOutboundRoute()

            por.name = form_result.get('name')
            por.customer_id = form_result.get('customer_id')
            por.gateway_id = form_result.get('gateway_id')
            por.pattern = form_result.get('pattern')

            db.add(por)
            db.commit(); db.flush(); db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully added outbound route."

    @authorize(super_user)
    def edit_outroute(self, **kw):
        schema = OutboundRouteForm()

        try:
            form_result = schema.to_python(request.params)
            por = PbxOutboundRoute.query.filter_by(id=form_result.get('outroute_id')).first()

            por.name = form_result.get('name')
            por.customer_id = form_result.get('customer_id')
            por.gateway_id = form_result.get('gateway_id')
            por.pattern = form_result.get('pattern')

            db.commit(); db.flush(); db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully edited outbound route."

    @authorize(super_user)
    def del_outroute(self, **kw):

        try:
            PbxOutboundRoute.query.filter_by(id=request.params.get('id')).delete()
            db.commit(); db.flush(); db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully deleted outbound route."

    @authorize(super_user)
    def dids(self):
        items=[]

        for row in db.query(PbxDid.id, PbxDid.did, Customer.name, Customer.id, Customer.context, PbxDid.active, PbxDid.t38, PbxDid.cnam, PbxDid.e911)\
            .filter(Customer.id==PbxDid.customer_id).order_by(PbxDid.did).all():
            items.append({'did': row[1],'customer_name': row[2], 'customer_id': row[3], 'context': row[4], 'active': row[5], 't38': row[6], 'cnam': row[7], 'e911': row[8]})
        db.remove()

        out = dict({'identifier': 'did', 'label': 'did', 'items': items})   #,'name': sorted(set(name)), 'id': sorted(set(id))})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def add_did(self, **kw):
        schema = DIDForm()
        try:
            form_result = schema.to_python(request.params)
            co = Customer.query.filter_by(name=form_result.get('customer_name', None)).first()
            if co:
                db.add(PbxDid(form_result.get('did_name', None), customer.id,
                    customer.context, customer.context, form_result.get('t38', False), form_result.get('e911', False),
                    form_result.get('cnam', False),form_result.get('active', False)))

                db.commit()
                db.flush()
            else:
                return "Error: Failed to insert DID."

        except validators.Invalid, error:
            db.remove()
            return 'Validation Error: %s' % error

        db.remove()
        return "Successfully added DID."

    @authorize(super_user)
    def update_did_grid(self, **kw):

        try:
            w = loads(urllib.unquote_plus(request.params.get("data")))

            for i in w['modified']:

                if i['customer_name'].isdigit():
                    customer = Customer.query.filter_by(id=i['customer_name']).first()
                else:
                    customer = Customer.query.filter_by(name=i['customer_name']).first()

                did = PbxDid.query.filter(PbxDid.did==i['did']).first()
                did.customer_id = customer.id
                did.context = customer.context
                did.domain = customer.context
                did.t38 = i['t38']
                did.cnam = i['cnam']
                did.e911 = i['e911']
                did.pbx_route_id = 0
                did.active = i['active']

                db.commit()
                db.flush()
                db.remove()

        except DataInputError, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully updated DID."

    @authorize(logged_in)
    def system_recordings(self):
        items = []
        dir = fs_vm_dir+session['context']+"/recordings/"
        try:
            for i in os.listdir(dir):
                fo = generateFileObject(i, "",  dir)
                items.append({'id': '1,'+fo["name"], 'name': 'Recording: '+fo["name"] , 'data': fo["path"], 'type': 1, 'real_id': ""})

            db.remove()
        except:
            pass
        out = dict({'identifier': 'id', 'label': 'name', 'items': items})

        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)

    @authorize(logged_in)
    def upload_system_recording(self):

        myfile = request.params['uploadedfiles[]']

        if not myfile.filename.endswith(".wav"):
            return "Error uploading file. File must have .wav extension."

        try:
            dir = fs_vm_dir + "/"+session['context']+"/system/recordings/"
            permanent_file = open(os.path.join(dir,myfile.filename.lstrip(os.sep)), 'w')
            shutil.copyfileobj(myfile.file, permanent_file)
            myfile.file.close()
            permanent_file.close()
        except:
            return "Error uploading file. The administrator has been contacted."

        return "Successfully uploaded recording."

    @authorize(super_user)
    def contexts(self, **kw):
        items=[]

        for row in PbxContext.query.all():
            customer = Customer.query.filter(Customer.id==row.customer_id).first()
            items.append({'id': row.id, 'context': row.context, 'profile': row.profile, 'caller_id_name': row.caller_id_name,
                          'caller_id_number': row.caller_id_number, 'customer_name': customer.name, 'gateway': row.gateway})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @jsonify
    @authorize(super_user)
    def context_by_id(self, id, **kw):
        items=[]
        try:
            row = PbxContext.query.filter(PbxContext.id==id).first()
            customer = Customer.query.filter(Customer.id==row.customer_id).first()
            items.append({'id': row.id, 'context': row.context, 'profile': row.profile, 'caller_id_name': row.caller_id_name,
                          'caller_id_number': row.caller_id_number, 'customer_name': customer.name, 'gateway': row.gateway})

            return {'identifier': 'id', 'label': 'name', 'items': items}

        except Exception, e:
            log.debug("Excepted: %s" % e)
            return {'identifier': 'id', 'label': 'name', 'items': [], 'error': str(e)}

    @authorize(super_user)
    def update_context_grid(self, **kw):

        try:
            w = loads(urllib.unquote_plus(request.params.get("data")))

            for i in w['modified']:

                if i['profile'].isdigit():
                    pro = PbxProfile.query.filter_by(id=i['profile']).first()
                else:
                    pro = PbxProfile.query.filter_by(name=i['profile']).first()

                if i['default_gateway'].isdigit():
                    gw = PbxGateway.query.filter_by(id=int(i['default_gateway'])).first()
                else:
                    gw = PbxGateway.query.filter_by(name=i['default_gateway']).first()

                com = Customer.query.filter_by(context=i['context']).first()

                con = PbxContext.query.filter_by(id=i['id']).first()
                con.pbx_profile_id = pro.id
                com.default_gateway = gw.name

                db.commit()
                db.flush()
                db.remove()

        except DataInputError, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully updated Gateway."

    @authorize(super_user)
    def add_context(self, **kw):
        schema = ContextForm()

        try:
            form_result = schema.to_python(request.params)

            context = PbxContext()

            context.customer_id = form_result.get('customer_id')
            context.profile = form_result.get('profile')
            context.domain = form_result.get('context')
            context.context = form_result.get('context')
            context.caller_id_name = form_result.get('caller_id_name')
            context.caller_id_number = form_result.get('caller_id_number')
            context.gateway = u'default'

            db.add(context)
            db.commit()

            db.flush()
            db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully added context."

    @authorize(super_user)
    def edit_context(self, **kw):
        schema = ContextEditForm()

        try:
            form_result = schema.to_python(request.params)

            context = PbxContext.query.filter(PbxContext.id==form_result.get('id')).first()

            context.profile = form_result.get('profile')
            context.caller_id_name = form_result.get('caller_id_name')
            context.caller_id_number = form_result.get('caller_id_number')
            context.gateway = form_result.get('gateway')

            db.add(context)
            db.flush()
            db.commit()
            db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully edited context."

    @authorize(super_user)
    def admins(self, **kw):
        items=[]
        for row in AdminUser.query.all():
            for r in row.permissions:
                log.debug("%s" % r)
            items.append({'id': row.id, 'name': row.first_name+' '+row.last_name, 'username': row.username, 'password': row.password, 'active': row.active})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def admin_by_id(self, id, **kw):
        items=[]
        row = AdminUser.query.filter(AdminUser.id==id).first()
        items.append({'id': row.id, 'first_name': row.first_name, 'last_name': row.last_name, 'username': row.username, 'password': row.password})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def add_admin(self, **kw):
        schema = AdminUserForm()

        try:
            form_result = schema.to_python(request.params)
            username = form_result.get('username')
            password = form_result.get('password')
            first_name = form_result.get('first_name')
            last_name = form_result.get('last_name')

            admin_user = AdminUser(username,password,first_name,last_name)
            Session.add(admin_user)

            admin_group = AdminGroup.query.filter_by(id=1).first()
            admin_group.admin_users.append(admin_user)
            Session.add(admin_group)

            db.commit()
            db.flush()
            db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully added admin user."

    @authorize(super_user)
    def edit_admin(self, **kw):
        schema = AdminEditUserForm()

        try:
            form_result = schema.to_python(request.params)
            user = AdminUser.query.filter(AdminUser.id==form_result.get('id')).first()
            user.password = form_result.get('password')
            user.first_name = form_result.get('first_name')
            user.last_name = form_result.get('last_name')

            db.commit()
            db.flush()
            db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully edited admin user."

    @authorize(super_user)
    def update_admin_grid(self, **kw):

        try:
            w = loads(urllib.unquote_plus(request.params.get("data")))

            for i in w['modified']:
                u = AdminUser.query.filter_by(id=i['id']).first()
                u.active = i['active']

                db.commit()
                db.flush()
                db.remove()

        except DataInputError, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully updated admin."

    @authorize(super_user)
    def delete_admin(self, **kw):

        if not len(AdminUser.query.all())>1:
            return "You only have one admin! Create another, then delete this one."
        try:
            if request.params.get('id', 0) == session['user_id']:
                logout=True
            au = AdminUser.query.filter(AdminUser.id==request.params.get('id', 0)).delete()
            db.commit()
            db.flush()
#            if logout:
#                redirect("/admin/logout")
#                return self.login()
        except Exception, e:
            db.remove()
            return "Error deleting admin: %s" % e

        db.remove()
        return  "Successfully deleted admin."


    @authorize(super_user)
    def cust_admins(self, **kw):
        items=[]
        perms=[]

        for row in User.query.all():
            for i in row.permissions:
                perms.append(str(i))

            if 'pbx_admin' in perms:
                items.append({'id': row.id, 'customer_name': row.get_customer_name(row.customer_id),
                              'active': row.active, 'perms': ','.join(perms),
                              'name': row.first_name+' '+row.last_name, 'first_name': row.first_name,
                              'last_name': row.last_name, 'username': row.username, 'password': row.password})
            perms=[]

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def cust_admin_by_id(self, id, **kw):
        items=[]
        row = User.query.filter_by(id=id).first()

        items.append({'id': row.id, 'customer_name': row.get_customer_name(row.customer_id), 'first_name': row.first_name, 'last_name': row.last_name, 'username': row.username, 'password': row.password, 'customer_id': row.customer_id, 'group_id': row.group_id})

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def add_cust_admin(self, **kw):
        schema = CustUserAdminForm()

        try:
            form_result = schema.to_python(request.params)
            username = form_result.get('username')
            password = form_result.get('password')
            first_name = form_result.get('first_name')
            last_name = form_result.get('last_name')

            u = User(first_name, last_name, username, password, form_result.get('customer_id'), True)
            db.add(u)

            g = Group.query.filter(Group.name=='pbx_admin').first()
            g.users.append(u)

            db.flush()
            db.commit()
            db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully added admin user."

    @authorize(super_user)
    def edit_cust_admin(self, **kw):
        schema = AdminUserForm()

        try:
            form_result = schema.to_python(request.params)
            user = User.query.filter(User.id==form_result.get('id')).first()
            user.password = form_result.get('password')
            user.first_name = form_result.get('first_name')
            user.last_name = form_result.get('last_name')

#            if form_result.get('group_id')>1:
#                if check_for_remaining_admin(user.customer_id)==1:
#                    return "Error: You are the last admin. Please make a new one before you lower "+user.username+"'s security level."

            db.execute("UPDATE user_groups set group_id = :group_id WHERE user_id = :user_id", {'group_id': form_result.get('group_id'), 'user_id': user.id})

            db.commit()
            db.flush()
            db.remove()

        except validators.Invalid, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully edited admin user."

    @authorize(super_user)
    def update_cust_admin_grid(self, **kw):

        try:
            w = loads(urllib.unquote_plus(request.params.get("data")))

            for i in w['modified']:
                u = User.query.filter_by(id=i['id']).first()
                u.active = i['active']

                db.commit()
                db.flush()
                db.remove()

        except DataInputError, error:
            db.remove()
            return 'Error: %s' % error

        return "Successfully updated admin."

    @authorize(super_user)
    def billing(self, **kw):
        return render('admin/billing.html')

    @authorize(super_user)
    def active_tickets(self):
        items=[]
        for row in Ticket.query.filter(Ticket.ticket_status_id!=4).all():
            items.append({'id': row.id, 'customer_id': row.customer_id, 'opened_by': row.opened_by,
                          'status': row.ticket_status_id, 'priority': row.ticket_priority_id,
                          'type': row.ticket_type_id, 'created': row.created.strftime("%m/%d/%Y %I:%M:%S %p"),
                          'expected_resolve_date': row.expected_resolve_date.strftime("%m/%d/%Y %I:%M:%S %p"),
                          'subject': row.subject, 'description': row.description})

        db.remove()

        out = dict({'identifier': 'id', 'label': 'id', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def closed_tickets(self):
        items=[]
        for row in Ticket.query.filter(Ticket.ticket_status_id==4).all():
            items.append({'id': row.id, 'customer_id': row.customer_id, 'opened_by': row.opened_by,
                          'status': row.ticket_status_id, 'priority': row.ticket_priority_id,
                          'type': row.ticket_type_id, 'created': row.created.strftime("%m/%d/%Y %I:%M:%S %p"),
                          'expected_resolve_date': row.expected_resolve_date.strftime("%m/%d/%Y %I:%M:%S %p"),
                          'subject': row.subject, 'description': row.description})

        db.remove()

        out = dict({'identifier': 'id', 'label': 'id', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)


    @authorize(super_user)
    def internal_tickets(self):
        items=[]
        for row in Ticket.query.filter(Ticket.ticket_status_id==7).all():
            items.append({'id': row.id, 'customer_id': row.customer_id, 'opened_by': row.opened_by,
                          'status': row.ticket_status_id, 'priority': row.ticket_priority_id,
                          'type': row.ticket_type_id, 'created': row.created.strftime("%m/%d/%Y %I:%M:%S %p"),
                          'expected_resolve_date': row.expected_resolve_date.strftime("%m/%d/%Y %I:%M:%S %p"),
                          'subject': row.subject, 'description': row.description})

        db.remove()

        out = dict({'identifier': 'id', 'label': 'id', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)


    @authorize(super_user)
    def ticket_data(self):
        ticket_status_id =[]
        ticket_status_name =[]
        ticket_type_id = []
        ticket_type_name = []
        ticket_priority_id = []
        ticket_priority_name = []
        opened_by_id = []
        opened_by_name = []

        for row in TicketStatus.query.all():
            ticket_status_id.append(row.id)
            ticket_status_name.append(row.name)
        for row in TicketType.query.all():
            ticket_type_id.append(row.id)
            ticket_type_name.append(row.name)
        for row in TicketPriority.query.all():
            ticket_priority_id.append(row.id)
            ticket_priority_name.append(row.name)
        for row in AdminUser.query.all():
            opened_by_id.append(row.id)
            opened_by_name.append(row.first_name+' '+row.last_name)

        db.remove()

        out = dict({'ticket_status_names': ticket_status_name, 'ticket_status_ids': ticket_status_id,
                    'ticket_type_names': ticket_type_name, 'ticket_type_ids': ticket_type_id,
                    'ticket_priority_names': ticket_priority_name, 'ticket_priority_ids': ticket_priority_id,
                    'opened_by_names': opened_by_name, 'opened_by_ids': opened_by_id})

        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def ticket_types(self):
        items=[]
        for row in TicketType.query.all():
            items.append({'id': row.id, 'name': row.name, 'description': row.description})

        db.remove()

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def ticket_statuses(self):
        items=[]
        for row in TicketStatus.query.all():
            items.append({'id': row.id, 'name': row.name, 'description': row.description})

        db.remove()

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def ticket_priorities(self):
        items=[]
        for row in TicketPriority.query.all():
            items.append({'id': row.id, 'name': row.name, 'description': row.description})

        db.remove()

        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)

    @authorize(super_user)
    def ticket_add(self, **kw):
        schema = TicketForm()
        try:
            form_result = schema.to_python(request.params)
            t = Ticket()
            t.subject = form_result.get('subject')
            t.description = form_result.get('description')
            t.customer_id = form_result.get('customer_id')
            t.opened_by = form_result.get('user_id')
            t.ticket_status_id = form_result.get('status_id')
            t.ticket_priority_id = form_result.get('priority_id')
            t.ticket_type_id = form_result.get('type_id')
            t.expected_resolution_date = form_result.get('expected_resolution_date')

            db.add(t)
            db.commit()
            db.flush()

        except validators.Invalid, error:
            db.remove()
            return 'Validation Error: %s' % error

        db.remove()
        return "Successfully added ticket."

    @authorize(super_user)
    def update_ticket_grid(self, **kw):

        w = loads(urllib.unquote_plus(request.params.get("data")))

        for i in w['modified']:
            ticket = Ticket.query.filter_by(id=i['id']).first()
            ticket.ticket_status_id = int(i['status'])
            ticket.ticket_type_id = int(i['type'])
            ticket.ticket_priority_id = int(i['priority'])

            db.commit()
            db.flush()
            db.remove()

        return "Successfully updated ticket."

    @authorize(logged_in)
    def channel_audio(self):

        def gen_file_object(filename, dir, root, expand=False, showHiddenFiles=False):
            path = dir+filename
            fullPath = path

            fObj = {}
            fObj["name"] = filename
            fObj["parentDir"] = dir
            fObj["path"] = path
            fObj["directory"] = os.path.isdir(fullPath)
            fObj["size"] = os.path.getsize(fullPath)
            fObj["modified"] = str(modification_date(fullPath)).strip("\"")

            children = []
            if os.path.isdir(fullPath):
                for o in os.listdir(fullPath):
                    if os.path.isdir(os.path.join(fullPath, o)):
                        fullpath =  os.path.join(fullPath, o)
                        path_arr = fullpath.split("/")
                        pts = path_arr[:-1]
                        dir = '/'.join(pts[5:])
                        children.append(gen_file_object(o, dir, root))
                    else:
                        children.append(o)
            fObj["children"] = children
            return fObj

        items = []
        dir = "/usr/local/freeswitch/recordings/channel_audio/"

        try:
            for i in os.listdir(dir):
                fo = gen_file_object(i, dir, "")
                items.append({'id': fo["name"], 'name': 'Recording: '+fo["name"] , 'data': fo["path"], 'type': 1, 'real_id': ""})
        except Exception, e:
            os.makedirs(dir)

        db.remove()
        out = dict({'identifier': 'id', 'label': 'name', 'items': items})
        response = make_response(out)
        response.headers = [("Content-type", 'application/json; charset=UTF-8'),]

        return response(request.environ, self.start_response)

    @authorize(logged_in)
    def upload_channel_audio(self):

        myfile = request.params['uploadedfiles[]']

        if not myfile.filename.endswith(".wav"):
            return "Error uploading file. File must have .wav extension."

        try:
            dir = "/usr/local/freeswitch/recordings/channel_audio/"
            permanent_file = open(os.path.join(dir,myfile.filename.lstrip(os.sep)), 'w')
            shutil.copyfileobj(myfile.file, permanent_file)
            myfile.file.close()
            permanent_file.close()
        except:
            return "Error uploading file."

        return "Successfully uploaded recording."

