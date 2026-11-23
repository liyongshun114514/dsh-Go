import 'package:dsh_app/state/goal_dock_state.dart';
import 'package:dsh_app/ui/chat/dock/dock_pill.dart';
import 'package:dsh_app/ui/chat/dock/dock_stack.dart';
import 'package:dsh_app/ui/chat/dock/goal_bar.dart';
import 'package:dsh_app/ui/chat/dock/todo_bar.dart';
import 'package:dsh_app/ui/chat/widgets/activity_strip.dart';
import 'package:dsh_app/ui/common/expand_reveal.dart';
import 'package:dsh_app/ui/plugins/native/composer_strip.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/harness.dart';
import 'support/dock_harness.dart';
import 'support/goal_fakes.dart';

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
        expect(filter.blendMode, BlendMode.src);
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
  });
}
