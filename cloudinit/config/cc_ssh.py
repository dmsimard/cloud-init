# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import glob
import os
import sys

# Ensure this is aliased to a name not 'distros'
# since the module attribute 'distros'
# is a list of distros that are supported, not a sub-module
from cloudinit import distros as ds

from cloudinit import ssh_util
from cloudinit import util

DISABLE_ROOT_OPTS = (
    "no-port-forwarding,no-agent-forwarding,"
    "no-X11-forwarding,command=\"echo \'Please login as the user \\\"$USER\\\""
    " rather than the user \\\"root\\\".\';echo;sleep 10\"")

GENERATE_KEY_NAMES = ['rsa', 'dsa', 'ecdsa', 'ed25519']
KEY_FILE_TPL = '/etc/ssh/ssh_host_%s_key'

CONFIG_KEY_TO_FILE = {}
PRIV_TO_PUB = {}
for k in GENERATE_KEY_NAMES:
    CONFIG_KEY_TO_FILE.update({"%s_private" % k: (KEY_FILE_TPL % k, 0o600)})
    CONFIG_KEY_TO_FILE.update(
        {"%s_public" % k: (KEY_FILE_TPL % k + ".pub", 0o600)})
    PRIV_TO_PUB["%s_private" % k] = "%s_public" % k

KEY_GEN_TPL = 'o=$(ssh-keygen -yf "%s") && echo "$o" root@localhost > "%s"'


def handle(_name, cfg, cloud, log, _args):

    # remove the static keys from the pristine image
    if cfg.get("ssh_deletekeys", True):
        key_pth = os.path.join("/etc/ssh/", "ssh_host_*key*")
        for f in glob.glob(key_pth):
            try:
                util.del_file(f)
            except:
                util.logexc(log, "Failed deleting key file %s", f)

    if "ssh_keys" in cfg:
        # if there are keys in cloud-config, use them
        for (key, val) in cfg["ssh_keys"].items():
            if key in CONFIG_KEY_TO_FILE:
                tgt_fn = CONFIG_KEY_TO_FILE[key][0]
                tgt_perms = CONFIG_KEY_TO_FILE[key][1]
                util.write_file(tgt_fn, val, tgt_perms)

        for (priv, pub) in PRIV_TO_PUB.items():
            if pub in cfg['ssh_keys'] or priv not in cfg['ssh_keys']:
                continue
            pair = (CONFIG_KEY_TO_FILE[priv][0], CONFIG_KEY_TO_FILE[pub][0])
            cmd = ['sh', '-xc', KEY_GEN_TPL % pair]
            try:
                # TODO(harlowja): Is this guard needed?
                with util.SeLinuxGuard("/etc/ssh", recursive=True):
                    util.subp(cmd, capture=False)
                log.debug("Generated a key for %s from %s", pair[0], pair[1])
            except:
                util.logexc(log, "Failed generated a key for %s from %s",
                            pair[0], pair[1])
    else:
        # if not, generate them
        genkeys = util.get_cfg_option_list(cfg,
                                           'ssh_genkeytypes',
                                           GENERATE_KEY_NAMES)
        lang_c = os.environ.copy()
        lang_c['LANG'] = 'C'
        for keytype in genkeys:
            keyfile = KEY_FILE_TPL % (keytype)
            if os.path.exists(keyfile):
                continue
            util.ensure_dir(os.path.dirname(keyfile))
            cmd = ['ssh-keygen', '-t', keytype, '-N', '', '-f', keyfile]

            # TODO(harlowja): Is this guard needed?
            with util.SeLinuxGuard("/etc/ssh", recursive=True):
                try:
                    out, err = util.subp(cmd, capture=True, env=lang_c)
                    sys.stdout.write(util.decode_binary(out))
                except util.ProcessExecutionError as e:
                    err = util.decode_binary(e.stderr).lower()
                    if (e.exit_code == 1 and
                            err.lower().startswith("unknown key")):
                        log.debug("ssh-keygen: unknown key type '%s'", keytype)
                    else:
                        util.logexc(log, "Failed generating key type %s to "
                                    "file %s", keytype, keyfile)

    try:
        (users, _groups) = ds.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ds.extract_default(users)
        disable_root = util.get_cfg_option_bool(cfg, "disable_root", True)
        disable_root_opts = util.get_cfg_option_str(cfg, "disable_root_opts",
                                                    DISABLE_ROOT_OPTS)

        keys = cloud.get_public_ssh_keys() or []
        if "ssh_authorized_keys" in cfg:
            cfgkeys = cfg["ssh_authorized_keys"]
            keys.extend(cfgkeys)

        apply_credentials(keys, user, disable_root, disable_root_opts)
    except:
        util.logexc(log, "Applying ssh credentials failed!")


def apply_credentials(keys, user, disable_root, disable_root_opts):

    keys = set(keys)
    if user:
        ssh_util.setup_user_keys(keys, user)

    if disable_root:
        if not user:
            user = "NONE"
        key_prefix = disable_root_opts.replace('$USER', user)
    else:
        key_prefix = ''

    ssh_util.setup_user_keys(keys, 'root', options=key_prefix)
