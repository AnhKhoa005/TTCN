#########################################################################
#
# Copyright (C) 2023 OSGeo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#########################################################################

"""Custom account providers for django-allauth.

These are used in order to extend the default authorization provided by
django-allauth.

"""
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.module_loading import import_string

from allauth.account.models import EmailAddress
from allauth.socialaccount.providers.base import AuthAction, ProviderAccount
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider

from geonode.people.adapters import GenericOpenIDConnectAdapter

PROVIDER_ID = getattr(settings, "SOCIALACCOUNT_OIDC_PROVIDER", "geonode_openid_connect")


def _pick_data(data):
    """Unwrap the OIDC payload into a flat claim mapping.

    django-allauth >= 65.11 hands the provider a *nested* dict:
    ``{"userinfo": {...}, "id_token": {...}}``, and its own providers call
    ``_pick_data()`` before reading any claim. This GeoNode provider predates
    that change and read ``data.get("sub")`` directly, so every lookup hit the
    nesting level and returned None, which allauth rejects with
    "uid must be a string: None". Userinfo is preferred because it carries
    more claims than the id_token, exactly as allauth does.
    """
    if not isinstance(data, dict):
        return data
    for key in ("userinfo", "id_token"):
        nested = data.get(key)
        if isinstance(nested, dict) and nested:
            return nested
    return data


class GenericOpenIDConnectProviderAccount(ProviderAccount):
    def to_str(self):
        dflt = super(GenericOpenIDConnectProviderAccount, self).to_str()
        return self.account.extra_data.get("name", dflt)


class GenericOpenIDConnectProvider(OAuth2Provider):
    id = "geonode_openid_connect"
    name = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {}).get(PROVIDER_ID, {}).get("NAME", "GeoNode OpenIDConnect")
    account_class = import_string(
        getattr(settings, "SOCIALACCOUNT_PROVIDERS", {})
        .get(PROVIDER_ID, {})
        .get(
            "ACCOUNT_CLASS",
            "geonode.people.socialaccount.providers.geonode_openid_connect.provider.GenericOpenIDConnectProviderAccount",
        )
    )
    oauth2_adapter_class = GenericOpenIDConnectAdapter

    @property
    def server_url(self):
        """In-cluster OIDC discovery endpoint, as seen from this process.

        django-allauth's OpenIDConnectOAuth2Adapter does
        ``sess.get(provider.server_url)`` and then reads the response as the
        provider's OIDC discovery document, so this must be the *discovery*
        endpoint. Two mistakes are easy to make here and both break the
        callback with a hard 500:

        * a bare host (``http://logto:3001``) makes Logto answer with a
          redirect to its browser-only /unknown-session page, which requests
          then follows and fails with ConnectionError;
        * omitting the ``/oidc`` base path yields a 404.

        SERVER_URL is the explicit override; otherwise the issuer - which is
        by definition the issuer of the id_token - supplies the base path, and
        only its host is swapped for the in-cluster one.
        """
        provider_settings = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {}).get(PROVIDER_ID, {})

        base = (provider_settings.get("SERVER_URL") or "").strip().rstrip("/")
        if base:
            if base.endswith("/.well-known/openid-configuration"):
                return base
            return f"{base}/.well-known/openid-configuration"

        issuer = (provider_settings.get("ID_TOKEN_ISSUER") or "").strip().rstrip("/")
        if not issuer:
            return ""
        # Keep the issuer's base path, but swap the public host for the
        # in-cluster one so the lookup never leaves the Docker network.
        parts = urlsplit(issuer)
        internal = provider_settings.get("SERVER_HOST") or "http://logto:3001"
        return f"{internal.rstrip('/')}{parts.path}/.well-known/openid-configuration"

    def get_default_scope(self):
        scope = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {}).get(PROVIDER_ID, {}).get("SCOPE", "")
        return scope

    def get_auth_params_from_request(self, request, action):
        ret = super(GenericOpenIDConnectProvider, self).get_auth_params_from_request(request, action)
        if action == AuthAction.REAUTHENTICATE:
            ret["prompt"] = (
                getattr(settings, "SOCIALACCOUNT_PROVIDERS", {})
                .get(PROVIDER_ID, {})
                .get("AUTH_PARAMS", {})
                .get("prompt", "")
            )
        return ret

    def extract_uid(self, data):
        data = _pick_data(data)
        _uid_field = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {}).get(PROVIDER_ID, {}).get("UID_FIELD", None)
        candidates = [_uid_field] if _uid_field else []
        candidates += ["sub", "uid", "id", "oid"]
        for candidate in candidates:
            if not candidate:
                continue
            value = data.get(candidate)
            # OIDC identifiers are strings; Logto returns them as such.
            if value is not None and str(value).strip():
                return str(value)
        return None

    def extract_common_fields(self, data):
        data = _pick_data(data)
        _common_fields = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {}).get(PROVIDER_ID, {}).get("COMMON_FIELDS", {})
        __common_fields_data = {}
        for _common_field in _common_fields:
            __common_fields_data[_common_field] = data.get(_common_fields.get(_common_field), "")
        return __common_fields_data

    def extract_email_addresses(self, data):
        data = _pick_data(data)
        addresses = []
        email = data.get("email")
        if email:
            addresses.append(
                EmailAddress(
                    email=email,
                    verified=data.get("email_verified", False),
                    primary=True,
                )
            )
        return addresses


provider_classes = [GenericOpenIDConnectProvider]
