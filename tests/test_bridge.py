import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Bridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = Bridge(dry_run=True, persist=False)
        self.session = self.bridge.connect(2)['session']
        self.bridge.config.update(x=100, y=50, width=800)

    def send(self, events, seq=0):
        self.bridge.events(dict(session=self.session, seq=seq, events=events))

    def test_mapping_and_pressure(self):
        self.send([dict(type='down', x=.25, y=.75, pressure=.8, tiltX=45)])
        self.assertEqual(self.bridge.last, dict(type='down', x=300, y=350, pressure=.8,
                                                tiltX=45, tiltY=0, pen=True, buttons=1,
                                                tabletX=.25*65535, tabletY=.75*65535, stylus=True))
        self.assertTrue(self.bridge.down)

    def test_release_preserves_position(self):
        self.send([dict(type='down', x=.5, y=.5)])
        self.bridge.release()
        self.assertFalse(self.bridge.down)
        self.assertEqual(self.bridge.last['type'], 'reset')
        self.assertEqual(self.bridge.last['x'], 500)

    def test_duplicate_not_replayed(self):
        event = dict(type='down', x=0, y=0)
        self.send([event])
        self.send([event])
        self.assertEqual(self.bridge.count, 1)

    def test_invalid_batch_is_atomic(self):
        with self.assertRaises(ValueError):
            self.send([dict(type='down', x=0, y=0), dict(type='move', x=float('nan'), y=0)])
        self.assertEqual(self.bridge.count, 0)

    def test_reconnect_releases_and_invalidates_old_client(self):
        self.send([dict(type='down', x=0, y=0)])
        self.bridge.connect(1.5)
        self.assertFalse(self.bridge.down)
        with self.assertRaises(ValueError): self.send([], seq=1)


    def test_touch_maps_to_screen_without_pen_state(self):
        self.send([dict(type='touch_down', x=.5, y=.5, buttons=1)])
        self.assertEqual(self.bridge.last, dict(type='touch_down', x=500, y=250, slot=1))
        self.assertFalse(self.bridge.down)

    def test_touch_slot_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            self.send([dict(type='touch_move', x=0, y=0, buttons=10)])


    def test_gesture_settings_merge_and_validate(self):
        updated = self.bridge.set_gestures(dict(zoomEnabled=False, panSpeed=2))
        self.assertFalse(updated['zoomEnabled'])
        self.assertTrue(updated['panEnabled'])
        self.assertEqual(updated['panSpeed'], 2)
        self.assertEqual(updated['pinchSlop'], 24)

    def test_gesture_settings_reject_bad_values_atomically(self):
        for bad in (dict(panEnabled='yes'), dict(panSpeed=99), dict(pinchSlop=float('nan'))):
            with self.assertRaises(ValueError):
                self.bridge.set_gestures(dict(bad, zoomSpeed=2))
        self.assertEqual(self.bridge.gestures['zoomSpeed'], 1)


if __name__ == '__main__': unittest.main()
