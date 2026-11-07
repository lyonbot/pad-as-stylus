import unittest
from unittest.mock import Mock
from usb import USBConnection


class BrowserSelectionTests(unittest.TestCase):
    def connection(self, packages):
        usb = USBConnection(18765)
        usb.run = Mock(side_effect=lambda *args: ''.join('package:'+p+'\n' for p in packages)
                       if 'pm' in args else 'Status: ok')
        return usb

    def test_beta_is_explicitly_selected_without_system_default(self):
        usb = self.connection(['com.chrome.beta'])
        self.assertTrue(usb.open_page('tablet'))
        args = usb.run.call_args.args
        self.assertEqual(args[-2:], ('-p', 'com.chrome.beta'))
        self.assertIn('http://127.0.0.1:18765/', args)

    def test_stable_preferred_when_both_installed(self):
        usb = self.connection(['com.chrome.beta', 'com.android.chrome'])
        usb.open_page('tablet')
        self.assertEqual(usb.run.call_args.args[-1], 'com.android.chrome')

    def test_missing_chrome_does_not_fall_back_to_edge(self):
        usb = self.connection(['com.microsoft.emmx'])
        self.assertFalse(usb.open_page('tablet'))
        self.assertTrue(all('am' not in call.args for call in usb.run.call_args_list))
        self.assertIn('未找到', usb.status)


if __name__ == '__main__': unittest.main()
