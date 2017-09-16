# -*- coding: utf-8 -*-
import contextlib

import requests
from bs4 import BeautifulSoup

from najdisi_sms import utils

log = utils.get_logger()


class SMSSender(object):
    """Docstring for SMSSender. """

    def __init__(self, username, password, useragent=""):
        """@todo: to be defined1. """
        self.username = username
        self.password = password
        da = "Mozilla/5.0 (Windows; U; Windows NT 6.1; es-ES; rv:1.9.2.3)" \
            + "Gecko/20100401 Firefox/3.6.3"
        self.useragent = useragent or da

        self._daily_max = None
        self._daily_left = None
        self._daily_send = None

    def get_values(self):
        self._login()

    @property
    def daily_max(self):
        if not self._daily_max:
            self.get_values()
        return self._daily_max

    @property
    def daily_send(self):
        if not self._daily_send:
            self.get_values()
        return self._daily_send

    @property
    def daily_left(self):
        if not self._daily_left:
            self._daily_left = self.daily_max - self.daily_send
        return self._daily_left

    def normalize_reciever(self, reciever_num):
        """
        Split telephone number into area code and local number.


        :reciever_num: Telephone number string.
        :returns: Tuple with area code and local number.

        """
        # 031 123 456
        who = reciever_num.strip()

        # don't change
        # 031 123 456 => 123456
        recipent = who.replace(' ', '')[3:]
        # 031 123 456 =>  031
        base_code = who[:3]

        return base_code, recipent

    def check_msg_leng(self, msg):
        """
        Checks the message length raises an exception if more than 160 chars.

        :msg: Message
        :returns: Returns non modified msg

        """
        if len(msg) > 160:
            raise Exception('Message to long')

        return msg

    @contextlib.contextmanager
    def _login(self, keep_session=False):
        self.s = requests.Session()

        self.s.headers.update({'User-Agent': self.useragent})

        response = self.s.get(
            'http://www.najdi.si/najdi.layoutnajdi.loginlink:login?t:ac=sms'
        )
        assert 'Pozabil/-a sem geslo' in response.text

        soup = BeautifulSoup(response.text, "html.parser")
        formdata_els = soup.findAll(attrs={'name': 't:formdata'})
        formdata_value = formdata_els[0].attrs['value']

        data = {
            't:formdata': formdata_value,
            'jsecLogin': self.username,
            'jsecPassword': self.password
        }
        response = self.s.post(
            'https://www.najdi.si/prijava.jsecloginform',
            data
        )
        assert 'Prejemnik' in response.text
        assert u'Pošiljatelj' in response.text
        assert 'poslani SMS-i' in response.text

        soup = BeautifulSoup(response.text, 'html.parser')

        smsno_div = soup.find('div', class_='smsno')
        self._daily_send, self._daily_max = \
            [int(value) for value in smsno_div.strong.text.split(' / ')]

        self._daily_left = self._daily_max - self._daily_send

        yield response

        if not keep_session:
            self.session.delete()

    def send(self, reciever, msg):
        """send the message.

        :reciever: reciever number (only Slovenian supported)
        :msg: SMS body message
        :returns: True if sending succeeded, else False.

        """

        msg = self.check_msg_leng(msg)

        base_code, recipient = self.normalize_reciever(reciever)

        log.info('Network code: %s', base_code)
        log.info('reciever: %s', recipient)
        log.info('Message: %s', msg)
        log.info('Sending SMS ...')

        with self._login(keep_session=True) as response:
            soup = BeautifulSoup(response.text, 'html.parser')

            formdata_els = soup.findAll(attrs={'name': 't:formdata'})
            formdata_vals = [formdata_el.attrs['value'] for
                             formdata_el in formdata_els]

            hidden_els = soup.findAll(attrs={'name': 'hidden'})
            hidden_value = hidden_els[0].attrs['value']

        data = {
            't:ac': 'sms',
            't:formdata': formdata_vals,
            'areaCodeRecipient': base_code,
            'phoneNumberRecipient': recipient,
            'selectLru': '',
            'hidden': hidden_value,
            'name': '',
            'text': msg,
            't:submit': '["send","send"]',
            't:zoneid': 'smsZone'
        }
        response = self.s.post(
            "http://www.najdi.si/"
            "najdi.shortcutplaceholder.freesmsshortcut.smsform",
            data,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )

        html_response = response.json()['content']
        assert 'Zaradi varnosti' in html_response

        soup = BeautifulSoup(html_response, 'html.parser')
        sender = soup.find('div', class_='sender').strong.text
        reciever = soup.find('div', class_='reciever').strong.text
        sent_text = soup.find('div', class_='msg').strong.text
        left_today = self._daily_left = \
            int(soup.find('div', class_='msgleft').strong.text)

        return_dict = {
            'sender': sender,
            'reciever': reciever,
            'text': sent_text,
            'left_today': left_today,
        }

        log.info('Sent message:\n%s', sent_text)
        log.info('Message left for today: %s', left_today)
        log.debug('%s', return_dict)

        self.s.close()

        return return_dict
