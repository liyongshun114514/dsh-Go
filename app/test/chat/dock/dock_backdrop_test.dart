import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:dsh_app/state/goal_dock_state.dart';
import 'package:dsh_app/ui/chat/dock/dock_pill.dart';
import 'package:dsh_app/ui/chat/dock/dock_stack.dart';
import 'package:dsh_app/ui/chat/dock/goal_bar.dart';
import 'package:dsh_app/ui/chat/dock/todo_bar.dart';
import 'package:dsh_app/ui/chat/widgets/activity_strip.dart';
import 'package:dsh_app/ui/common/expand_reveal.dart';
import 'package:dsh_app/ui/plugins/native/composer_strip.dart';
import 'package:dsh_app/ui/theme/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/harness.dart';
import 'support/dock_harness.dart';
import 'support/goal_fakes.dart';

// Capture the background and the filter together. Capturing just the pill's
// repaint boundary would give BackdropFilter an empty, transparent backdrop.
const _captureKey = ValueKey('dock-pixel-scene');

Widget _pixelScene(
  Widget dock, {
  required Color background,
  Brightness brightness = Brightness.light,
  bool shadows = false,
}) => testApp(
  Scaffold(
    body: Builder(
      builder: (context) {
        final theme = Theme.of(context);
        final surfaces = DshSurfaces.of(context);
        return Theme(
          data: theme.copyWith(extensions: [
            for (final extension in theme.extensions.values)
              if (extension is! DshSurfaces) extension,
            // Keep the production fill, bounded blur and saturation. Remove
            // only shadows, so gap pixels have an exact background oracle.
            shadows ? surfaces : surfaces.copyWith(chrome: surfaces.chrome.copyWith(shadows: const [])),
          ]),
          child: RepaintBoundary(
            key: _captureKey,
            child: ColoredBox(
              color: background,
              child: Align(
                alignment: Alignment.bottomCenter,
                child: Padding(padding: const EdgeInsets.fromLTRB(16, 0, 16, 80), child: dock),
              ),
            ),
          ),
        );
      },
    ),
  ),
  brightness: brightness,
);

class _Pixels {
  const _Pixels(this.width, this.height, this.bytes);

  final int width;
  final int height;
  final Uint8List bytes;

  static Future<_Pixels> capture(WidgetTester tester, String name) async {
    final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(_captureKey));
    return (await tester.runAsync(() async {
      final image = await boundary.toImage(pixelRatio: 1);
      try {
        final previewDir = Platform.environment['DSH_DOCK_PREVIEW_DIR'];
        if (previewDir != null && previewDir.isNotEmpty) {
          await Directory(previewDir).create(recursive: true);
          final png = (await image.toByteData(format: ui.ImageByteFormat.png))!;
          await File('$previewDir/$name.png').writeAsBytes(png.buffer.asUint8List());
        }
        final data = (await image.toByteData(format: ui.ImageByteFormat.rawRgba))!;
        return _Pixels(image.width, image.height, Uint8List.fromList(data.buffer.asUint8List()));
      } finally {
        image.dispose();
      }
    }))!;
  }

  Color at(Offset point) {
    final index = (point.dy.round() * width + point.dx.round()) * 4;
    return Color.fromARGB(bytes[index + 3], bytes[index], bytes[index + 1], bytes[index + 2]);
  }

  void expectPatch(Offset center, Color expected, {required String reason}) {
    final x = center.dx.round();
    final y = center.dy.round();
    expect(x, inInclusiveRange(1, width - 2), reason: reason);
    expect(y, inInclusiveRange(1, height - 2), reason: reason);
    // A tiny patch, not a text/rim/antialiased edge pixel or a whole-image
    // average that could hide a small dark rectangular regression.
    for (var dy = -1; dy <= 1; dy++) {
      for (var dx = -1; dx <= 1; dx++) {
        final index = ((y + dy) * width + x + dx) * 4;
        final channels = [expected.r, expected.g, expected.b, expected.a];
        for (var channel = 0; channel < 4; channel++) {
          expect(bytes[index + channel], closeTo(channels[channel] * 255, 5), reason: '$reason, channel $channel');
        }
      }
    }
  }
}

Rect _inScene(WidgetTester tester, Finder finder) {
  final origin = tester.getTopLeft(find.byKey(_captureKey));
  final box = tester.renderObject<RenderBox>(finder);
  return Rect.fromPoints(
    box.localToGlobal(Offset.zero) - origin,
    box.localToGlobal(box.size.bottomRight(Offset.zero)) - origin,
  );
}

Offset _blankTop(Rect rect) => Offset(rect.center.dx, rect.top + 3);

List<Widget> _realCards() => [
  DockSlot(child: TodoBar(summary: TodoDockSummary.of(todosRunning, running: true)!)),
  DockSlot(child: GoalBar(goal: DockGoal(projection: goalOf()))),
  DockSlot(child: ActivityStrip(activity: dockStrip(), whale: false)),
  const DockSlot(child: ComposerStrip(package: 'test', title: 'Test', text: 'Ready')),
];

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('real dock filters stay independent through folding and fading', (tester) async {
    usePhoneView(tester);
    await tester.pumpWidget(testApp(Scaffold(
      body: Align(
        alignment: Alignment.bottomCenter,
        child: BackdropGroup(
          child: DockStack(cards: [
            DockSlot(child: TodoBar(summary: TodoDockSummary.of(todosRunning, running: true)!)),
            DockSlot(child: GoalBar(goal: DockGoal(projection: goalOf()))),
            DockSlot(child: ActivityStrip(activity: dockStrip(), whale: false)),
            const DockSlot(child: ComposerStrip(package: 'test', title: 'Test', text: 'Ready')),
          ]),
        ),
      ),
    )));
    await pumpFrames(tester);

    void checkFilters() {
      final filters = tester.renderObjectList<RenderBackdropFilter>(find.descendant(
        of: find.byType(DockStack),
        matching: find.byType(BackdropFilter),
      )).toList();
      // Four real cards plus the fold button, not a scope-only mock.
      expect(filters, hasLength(5));
      for (final filter in filters) {
        expect(filter.backdropKey, isNull);
        expect(filter.blendMode, BlendMode.srcOver);
        expect(filter.enabled, isTrue);
      }
      expect(tester.takeException(), isNull);
    }

    double height() => tester.getSize(find.byType(DockStack)).height;
    final foldedHeight = height();
    expect(find.byKey(const ValueKey('dock-fold')).hitTestable(), findsNothing);
    checkFilters();
    await tester.tap(find.byType(ComposerStrip));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 80));
    expect(height(), greaterThan(foldedHeight));
    checkFilters();
    await pumpFrames(tester);
    final spreadHeight = height();
    expect(spreadHeight, greaterThan(foldedHeight));
    expect(find.byKey(const ValueKey('dock-fold')).hitTestable(), findsOneWidget);
    checkFilters();
    await tester.tap(find.byKey(const ValueKey('dock-fold')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 80));
    expect(height(), lessThan(spreadHeight));
    checkFilters();
    await pumpFrames(tester);
    expect(height(), closeTo(foldedHeight, 0.01));
    checkFilters();
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final brightness in Brightness.values) {
    testWidgets('single goal samples its real background (${brightness.name})', (tester) async {
      usePhoneView(tester);
      final base = testTheme(brightness).extension<DshSurfaces>()!;
      expect(base.blurEnabled, isTrue);
      for (final background in [const Color(0xFFF0F0F0), const Color(0xFFA0A0A0)]) {
        await tester.pumpWidget(_pixelScene(
          DockStack(cards: [DockSlot(child: GoalBar(goal: DockGoal(projection: goalOf())))]),
          background: background,
          brightness: brightness,
        ));
        await pumpFrames(tester);
        final pixels = await _Pixels.capture(tester, 'goal-${brightness.name}-${background.toARGB32()}');
        final goal = _inScene(tester, find.byType(GoalBar));
        // Saturation preserves neutral gray; white/smoke fill is composited
        // over the actual sampled gray, not a black or empty save layer.
        final expected = Color.alphaBlend(base.chrome.fill, background);
        pixels.expectPatch(_blankTop(goal), expected, reason: 'goal on $background');
        pixels.expectPatch(Offset(goal.center.dx, goal.bottom + 3), background, reason: 'goal gap');
        final reveal = tester.widget<ExpandReveal>(find.descendant(
          of: find.byType(DockSlot),
          matching: find.byType(ExpandReveal),
        ));
        expect(reveal.fade, isFalse);
        expect(
          find.descendant(
            of: find.byType(DockStack),
            matching: find.ancestor(of: find.byType(BackdropFilter).first, matching: find.byType(FadeTransition)),
          ),
          findsNothing,
        );
        await tester.pumpWidget(const SizedBox.shrink());
      }
    });
  }

  testWidgets('real folded peeks and spread transitions preserve light glass pixels', (tester) async {
    usePhoneView(tester);
    const background = Color(0xFFF0F0F0);
    final expected = Color.alphaBlend(testTheme(Brightness.light).extension<DshSurfaces>()!.chrome.fill, background);
    await tester.pumpWidget(_pixelScene(
      BackdropGroup(child: DockStack(cards: _realCards())),
      background: background,
    ));
    await pumpFrames(tester);

    Future<void> checkPixels(String phase) async {
      final pixels = await _Pixels.capture(tester, 'deck-${phase.replaceAll(' ', '-')}');
      final cards = [
        _inScene(tester, find.byType(TodoBar)),
        _inScene(tester, find.byType(GoalBar)),
        _inScene(tester, find.byType(ActivityStrip)),
        _inScene(tester, find.byType(ComposerStrip)),
      ];
      // Four cards leave two visible peeks: todo is completely hidden when
      // folded. Goal/activity top patches are inside those clipped peeks.
      for (var i = 1; i < cards.length; i++) {
        pixels.expectPatch(_blankTop(cards[i]), expected, reason: '$phase card $i');
      }
      // As cards separate, a gap is only exposed once the lower card starts
      // below the complete preceding pill (not merely its folded peek).
      for (var i = 0; i < cards.length - 1; i++) {
        final upper = cards[i];
        final lower = cards[i + 1];
        if (lower.top - upper.bottom >= 5) {
          pixels.expectPatch(
            Offset(upper.center.dx, (upper.bottom + lower.top) / 2),
            background,
            reason: '$phase gap $i',
          );
        }
      }
      pixels.expectPatch(Offset(cards.last.center.dx, cards.last.bottom + 3), background, reason: '$phase bottom gap');
      expect(tester.takeException(), isNull);
    }

    await checkPixels('folded');
    await tester.tap(find.byType(ComposerStrip));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 80));
    await checkPixels('spreading');
    await pumpFrames(tester);
    await checkPixels('spread');
    await tester.tap(find.byKey(const ValueKey('dock-fold')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 80));
    await checkPixels('folding');
    await pumpFrames(tester);
    await checkPixels('folded again');
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('real glass shadow continues below the slot and single-card stack', (tester) async {
    usePhoneView(tester);
    final previousDisableShadows = debugDisableShadows;
    debugDisableShadows = false;
    // The binding verifies painting globals before addTearDown callbacks run.
    // Restore in the test body, including when a pixel assertion throws.
    try {
      const background = Color(0xFFF0F0F0);
      List<Color>? reference;
      for (final placement in ['bare', 'slot', 'stack']) {
        Widget goal = GoalBar(goal: DockGoal(projection: goalOf()));
        if (placement != 'bare') goal = DockSlot(child: goal);
        if (placement == 'stack') goal = DockStack(cards: [goal]);
        await tester.pumpWidget(_pixelScene(goal, background: background, shadows: true));
        await pumpFrames(tester);
        final rect = _inScene(tester, find.byType(GoalBar));
        final pixels = await _Pixels.capture(tester, 'shadow-$placement');
        final samples = [
          for (final distance in [3.0, 9.0, 18.0]) pixels.at(Offset(rect.center.dx, rect.bottom + distance)),
        ];
        // Nine pixels below the pill is beyond DockSlot's six-pixel gap.
        // A hard slot clip would abruptly restore the untouched background.
        expect(samples[1].r, lessThan(background.r - 1 / 255), reason: '$placement shadow beyond slot');
        expect(samples[2].computeLuminance(), greaterThan(samples[0].computeLuminance()), reason: '$placement shadow fades');
        if (reference != null) {
          for (var i = 0; i < samples.length; i++) {
            for (final pair in [(samples[i].r, reference[i].r), (samples[i].g, reference[i].g), (samples[i].b, reference[i].b)]) {
              expect(pair.$1, closeTo(pair.$2, 2 / 255), reason: '$placement matches unclipped bare shadow at $i');
            }
          }
        }
        reference = samples;
        await tester.pumpWidget(const SizedBox.shrink());
      }
    } finally {
      debugDisableShadows = previousDisableShadows;
    }
  });

  testWidgets('dock shadow is unclipped only after the reveal completes', (tester) async {
    usePhoneView(tester);
    final visible = ValueNotifier(true);
    addTearDown(visible.dispose);
    await tester.pumpWidget(testApp(Scaffold(
      body: ValueListenableBuilder<bool>(
        valueListenable: visible,
        builder: (context, open, _) => Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            DockSlot(child: open ? const SizedBox(height: 36, child: Text('bar')) : null),
            ExpandReveal(open: open, child: const SizedBox(height: 36, child: Text('ordinary'))),
          ],
        ),
      ),
    )));
    await pumpFrames(tester);
    Clip clipUnder(Type type) => tester.widget<ClipRect>(find.descendant(
      of: find.byType(type).first,
      matching: find.byType(ClipRect),
    ).first).clipBehavior;
    expect(clipUnder(DockSlot), Clip.none);
    expect(clipUnder(ExpandReveal), Clip.none);
    final ordinaryClip = find.descendant(
      of: find.byType(ExpandReveal).last,
      matching: find.byType(ClipRect),
    ).first;
    expect(tester.widget<ClipRect>(ordinaryClip).clipBehavior, Clip.hardEdge);
    visible.value = false;
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 40));
    expect(clipUnder(DockSlot), Clip.hardEdge);
    expect(find.text('bar'), findsOneWidget);
    await pumpFrames(tester);
    expect(find.text('bar'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
