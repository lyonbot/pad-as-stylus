"""Exercise the actual Swift event generator without posting OS input."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeLifecycleTests(unittest.TestCase):
    def trace(self, *events):
        result = subprocess.run([str(ROOT / '.build/PenBridge'), '--trace'],
                                input=''.join(json.dumps(e) + '\n' for e in events),
                                text=True, capture_output=True, check=True)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def event(self, kind, x=100, y=200, **extra):
        return dict(type=kind, x=x, y=y, pen=True, **extra)

    def test_hover_down_drag_up_hover_leave(self):
        events = self.trace(self.event('enter'), self.event('move', x=110, buttons=0),
                            self.event('down', x=110, pressure=.4, buttons=1),
                            self.event('move', x=120, pressure=.8, buttons=1),
                            self.event('up', x=120, pressure=.9, buttons=0),
                            self.event('move', x=130, pressure=.7, buttons=0), self.event('leave'))
        self.assertEqual([e['event'] for e in events],
                         ['proximityEnter', 'hover', 'hover', 'down', 'drag', 'up', 'hover', 'proximityLeave'])
        self.assertEqual(events[4]['pressure'], .8)
        self.assertEqual(events[5]['pressure'], 0)
        self.assertEqual(events[6]['pressure'], 0)
        self.assertEqual(events[3]['stroke'], events[5]['stroke'])

    def test_cancel_releases_at_last_position_and_blocks_stray_moves(self):
        events = self.trace(self.event('down', pressure=.8, buttons=1),
                            self.event('cancel', x=999), self.event('move', x=999, buttons=1))
        self.assertEqual([e['event'] for e in events], ['proximityEnter', 'down', 'up', 'proximityLeave'])
        self.assertEqual(events[2]['x'], 100)

    def test_new_enter_after_cancel_recovers_hover(self):
        events = self.trace(self.event('down'), self.event('cancel'), self.event('enter', x=300))
        self.assertEqual([e['event'] for e in events][-3:], ['proximityEnter', 'hover', 'proximityLeave'])
        self.assertEqual(events[-2]['x'], 300)

    def test_pressure_only_uses_native_tablet_point(self):
        events = self.trace(self.event('down', pressure=.3, buttons=1),
                            self.event('move', pressure=.7, buttons=1), self.event('up'))
        self.assertEqual(events[2]['event'], 'tabletPoint')
        self.assertEqual(events[2]['pressure'], .7)

    def test_missing_up_recovers_from_button_state(self):
        events = self.trace(self.event('down', buttons=1), self.event('move', x=150, buttons=0))
        self.assertEqual([e['event'] for e in events], ['proximityEnter', 'down', 'up', 'hover', 'proximityLeave'])

    def test_eof_releases_before_leaving_proximity(self):
        events = self.trace(self.event('down', buttons=1))
        self.assertEqual([e['event'] for e in events], ['proximityEnter', 'down', 'up', 'proximityLeave'])

    def test_plain_mouse_mode_has_no_proximity(self):
        events = self.trace(dict(type='down', x=10, y=20, pen=False),
                            dict(type='move', x=30, y=40, buttons=1, pen=False),
                            dict(type='up', x=30, y=40, pen=False))
        self.assertEqual([e['event'] for e in events], ['down', 'drag', 'up'])

    def test_mouse_right_and_middle_buttons_use_correct_drag_types(self):
        for buttons, button, expected in ((2, 1, [3, 7, 4]), (4, 2, [25, 27, 26]),
                                          (8, 3, [25, 27, 26]), (16, 4, [25, 27, 26])):
            with self.subTest(button=button):
                events = self.trace(dict(type='down', x=10, y=20, buttons=buttons, pen=False),
                                    dict(type='move', x=30, y=40, buttons=buttons, pen=False),
                                    dict(type='up', x=30, y=40, buttons=0, pen=False))
                self.assertEqual([e['cgType'] for e in events], expected)
                self.assertEqual([e['button'] for e in events], [button]*3)
                self.assertEqual(events[0]['stroke'], events[2]['stroke'])

    def test_mouse_drag_delta_and_default_subtype(self):
        events = self.trace(dict(type='enter', x=10, y=20, pen=False),
                            dict(type='move', x=25, y=30, buttons=0, pen=False),
                            dict(type='down', x=25, y=30, buttons=1, pen=False),
                            dict(type='move', x=40, y=50, buttons=1, pen=False),
                            dict(type='up', x=40, y=50, buttons=0, pen=False))
        self.assertEqual((events[1]['deltaX'], events[1]['deltaY']), (15, 10))
        self.assertEqual((events[3]['deltaX'], events[3]['deltaY']), (15, 20))
        self.assertEqual(events[3]['cgType'], 6)
        self.assertTrue(all(e['subtype'] == 0 for e in events))

    def test_mouse_chord_transitions_and_drag_button(self):
        events = self.trace(dict(type='down', x=10, y=20, buttons=1, pen=False),
                            dict(type='move', x=20, y=30, buttons=3, pen=False),
                            dict(type='move', x=30, y=40, buttons=2, pen=False),
                            dict(type='up', x=30, y=40, buttons=0, pen=False))
        self.assertEqual([e['cgType'] for e in events], [1, 3, 6, 2, 7, 4])
        self.assertEqual(events[-1]['held'], 0)

    def test_mouse_cancel_releases_all_buttons_without_jumping(self):
        events = self.trace(dict(type='down', x=10, y=20, buttons=3, pen=False),
                            dict(type='cancel', x=999, y=999, pen=False),
                            dict(type='move', x=999, y=999, buttons=3, pen=False))
        self.assertEqual([e['cgType'] for e in events], [1, 3, 2, 4])
        self.assertEqual(events[-1]['x'], 10)
        self.assertEqual(events[-1]['held'], 0)

    def test_mouse_double_click_survives_normal_pen_leaving_range(self):
        events = self.trace(dict(type='down', x=10, y=20, buttons=1, pen=False),
                            dict(type='up', x=10, y=20, buttons=0, pen=False),
                            dict(type='leave', pen=False), dict(type='enter', x=10, y=20, pen=False),
                            dict(type='down', x=10, y=20, buttons=1, pen=False),
                            dict(type='up', x=10, y=20, buttons=0, pen=False))
        self.assertEqual([e['clickCount'] for e in events if e['event'] == 'down'], [1, 2])
        self.assertEqual([e['clickCount'] for e in events if e['event'] == 'up'], [1, 2])

    def test_pen_side_button_does_not_hold_tip_down_after_tip_lifts(self):
        events = self.trace(self.event('down', buttons=2),
                            self.event('move', x=110, buttons=3, pressure=.5),
                            self.event('move', x=120, buttons=2, pressure=0),
                            self.event('up', buttons=0))
        names = [e['event'] for e in events]
        self.assertEqual(names.count('down'), 1)
        self.assertEqual(names.count('up'), 1)
        self.assertEqual(names[-2:], ['hover', 'proximityLeave'])

    def test_barrel_plus_tip_is_right_click_and_drag_in_both_modes(self):
        for pen in (False, True):
            with self.subTest(pen=pen):
                events = self.trace(dict(type='down', x=100, y=200, buttons=3, pressure=.5, pen=pen, stylus=True),
                                    dict(type='move', x=120, y=220, buttons=1, pressure=.6, pen=pen, stylus=True),
                                    dict(type='up', x=120, y=220, buttons=0, pen=pen, stylus=True))
                clicks = [e for e in events if e['event'] in ('down', 'drag', 'up')]
                self.assertEqual([e['cgType'] for e in clicks], [3, 7, 4])
                self.assertEqual([e['button'] for e in clicks], [1, 1, 1])

    def test_mouse_stylus_barrel_alone_never_clicks(self):
        events = self.trace(dict(type='enter', x=100, y=200, buttons=2, pen=False, stylus=True),
                            dict(type='down', x=100, y=200, buttons=2, pen=False, stylus=True),
                            dict(type='move', x=120, y=220, buttons=2, pen=False, stylus=True),
                            dict(type='up', x=120, y=220, buttons=0, pen=False, stylus=True))
        self.assertEqual([e['event'] for e in events], ['hover', 'hover'])

    def test_mouse_stylus_tip_press_during_barrel_hold_starts_right_drag(self):
        events = self.trace(dict(type='down', x=100, y=200, buttons=2, pen=False, stylus=True),
                            dict(type='move', x=110, y=210, buttons=3, pen=False, stylus=True),
                            dict(type='move', x=120, y=220, buttons=2, pen=False, stylus=True),
                            dict(type='up', x=120, y=220, buttons=0, pen=False, stylus=True))
        self.assertEqual([e['cgType'] for e in events], [3, 7, 4, 5])

    def test_mouse_stylus_reset_does_not_restart_a_held_tip(self):
        events = self.trace(dict(type='down', x=100, y=200, buttons=3, pen=False, stylus=True),
                            dict(type='reset', pen=False, stylus=True),
                            dict(type='move', x=120, y=220, buttons=3, pen=False, stylus=True),
                            dict(type='move', x=120, y=220, buttons=0, pen=False, stylus=True),
                            dict(type='down', x=120, y=220, buttons=3, pen=False, stylus=True))
        clicks = [e['cgType'] for e in events if e['event'] in ('down', 'up')]
        self.assertEqual(clicks, [3, 4, 3, 4])


class TouchGestureTests(NativeLifecycleTests):
    def touch(self, kind, slot, x, y):
        return dict(type='touch_' + kind, slot=slot, x=x, y=y)

    def scrolls(self, *events):
        return [(e['phase'], e['dx'], e['dy']) for e in self.trace(*events) if e['event'] == 'scroll']

    def two_down(self):
        return [self.touch('down', 0, 100, 100), self.touch('down', 1, 200, 100)]

    def test_two_finger_pan_is_phased_and_follows_centroid(self):
        out = self.scrolls(*self.two_down(), self.touch('move', 0, 100, 104),
                           self.touch('move', 0, 100, 120), self.touch('move', 1, 200, 130),
                           self.touch('up', 1, 200, 130))
        self.assertEqual(out, [(1, 0, 10), (2, 0, 15), (4, 0, 0)])

    def test_pan_waits_while_finger_spacing_is_changing(self):
        # Centroid moved 30pt but spacing changed 16.6pt: neither a clean pan nor a pinch yet.
        self.assertEqual(self.trace(*self.two_down(), self.touch('move', 0, 100, 160)), [])

    def test_single_finger_and_small_jitter_do_not_scroll(self):
        self.assertEqual(self.scrolls(self.touch('down', 0, 0, 0), self.touch('move', 0, 0, 90)), [])
        self.assertEqual(self.scrolls(*self.two_down(), self.touch('move', 0, 100, 103)), [])

    def test_third_finger_ends_pan_until_all_lift(self):
        out = self.scrolls(*self.two_down(), self.touch('move', 0, 100, 120),
                           self.touch('down', 2, 300, 100), self.touch('move', 0, 100, 200),
                           self.touch('up', 2, 300, 100), self.touch('move', 0, 100, 260))
        self.assertEqual([p for p, _, _ in out], [1, 4])

    def test_small_finger_spread_change_does_not_zoom(self):
        self.assertEqual(self.magnifies(*self.two_down(), self.touch('move', 1, 220, 100)), [])

    def magnifies(self, *events):
        return [(e['phase'], e['magnification']) for e in self.trace(*events) if e['event'] == 'magnify']

    def test_pinch_out_magnifies_by_relative_distance_change(self):
        out = self.magnifies(*self.two_down(), self.touch('move', 1, 230, 100),
                             self.touch('move', 1, 250, 100), self.touch('up', 1, 250, 100))
        self.assertEqual([p for p, _ in out], [1, 2, 2, 4])
        self.assertAlmostEqual(out[1][1], .3)
        self.assertAlmostEqual(out[2][1], 20 / 130)
        self.assertEqual(out[3][1], 0)

    def test_pinch_in_is_negative_and_never_scrolls(self):
        events = self.trace(*self.two_down(), self.touch('move', 0, 130, 100), self.touch('move', 1, 170, 100))
        self.assertEqual([e['event'] for e in events], ['magnify'] * 4)
        self.assertTrue(all(e['magnification'] <= 0 for e in events))

    def test_gesture_mode_stays_locked(self):
        events = self.trace(*self.two_down(), self.touch('move', 1, 230, 100),
                            self.touch('move', 0, 100, 300), self.touch('move', 1, 230, 300))
        self.assertEqual({e['event'] for e in events}, {'magnify'})

    def configure(self, **settings):
        return dict(type='gestures', **settings)

    def test_gestures_can_be_disabled_independently(self):
        pinch = [*self.two_down(), self.touch('move', 1, 260, 100)]
        pan = [*self.two_down(), self.touch('move', 0, 100, 140), self.touch('move', 1, 200, 140)]
        self.assertEqual(self.trace(self.configure(zoomEnabled=False), *pinch), [])
        self.assertEqual(self.trace(self.configure(panEnabled=False), *pan), [])
        self.assertTrue(self.trace(self.configure(zoomEnabled=False), *pan))

    def test_speed_and_thresholds_apply(self):
        out = self.scrolls(self.configure(panSpeed=2, panSlop=2), *self.two_down(),
                           self.touch('move', 0, 100, 104), self.touch('move', 1, 200, 104))
        self.assertEqual(out[0], (1, 0, 8))
        phase, amount = self.magnifies(self.configure(zoomSpeed=.5, pinchSlop=4), *self.two_down(),
                                       self.touch('move', 1, 210, 100))[1]
        self.assertEqual(phase, 2)
        self.assertAlmostEqual(amount, .05)

    def test_reset_ends_active_pan(self):
        out = self.scrolls(*self.two_down(), self.touch('move', 0, 100, 120), dict(type='reset', x=0, y=0))
        self.assertEqual([p for p, _, _ in out], [1, 4])


if __name__ == '__main__': unittest.main()
