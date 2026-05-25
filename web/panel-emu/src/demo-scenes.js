// Visual DCP demo scenes — built around a 6×6 grid with a movable square.
// The LLM calls move(dir, step); DCP gates calls that go out of bounds or
// lack capability. Audience sees pixels move (or NOT move) — no jargon
// needed to grok safety.
//
// Step kinds:
//   { kind: 'set_status', text }
//   { kind: 'narrate', line, role, text }    line ∈ {0,1,2}
//   { kind: 'move', dx, dy }                  move + DCP-OK animation
//   { kind: 'try_move', dx, dy }              attempt that bridge will reject
//   { kind: 'flash', flash }                  '' | 'ok' | 'err'
//   { kind: 'ghost', x, y }  or  { kind: 'ghost', clear: true }
//   { kind: 'pos', x, y }                     set absolute position
//   { kind: 'clear_narration' }
//   { kind: 'pause', ms }
//   { kind: 'view', view: 'demo'|'briefing'|'grid' }

const wait = (ms) => ({ kind: 'pause', ms });

export const SCENES = [
  // ────────────────────────────────────────────────────────────────
  {
    tag: '[1/3] HOW THIS WORKS',
    description: 'Sets up the grid + LLM + DCP scenario',
    briefing: {
      testing:    'A language model (LLM) has been given ONE tool: move(direction, steps). It can move the green square around a 6×6 grid. The DCP protocol sits between the LLM and the grid — every move call goes through it.',
      mechanism:  'DCP looks up the move intent in a manifest, checks parameters against declared ranges, and dispatches if safe. Out-of-bounds moves get rejected at the bridge — the square never moves.',
      watch:      'In scene 2, watch the LLM happily move the square around. In scene 3, watch what happens when it tries to leave the grid.',
      expected:   'You will see WHY DCP exists: it stops bad calls before any side effect.',
    },
    steps: [
      { kind: 'view', view: 'grid' },
      { kind: 'set_status', text: '[1/3] HOW THIS WORKS' },
      { kind: 'pos', x: 0, y: 0 },
      { kind: 'narrate', line: 0, role: 'user',   text: 'USER: meet the grid + the square' },
      { kind: 'narrate', line: 1, role: 'plain',  text: 'LLM tool: move(dir, step)' },
      { kind: 'narrate', line: 2, role: 'dcp_ok', text: 'DCP gates every move' },
      wait(5000),
    ],
  },

  // ────────────────────────────────────────────────────────────────
  {
    tag: '[2/3] LLM MOVES THE SQUARE',
    description: 'LLM plans a path; each move passes the DCP range check',
    briefing: {
      testing:    'Happy path. The LLM is told "walk a small loop". It picks moves; DCP validates each one; the square animates.',
      mechanism:  'For each call, the bridge checks the new position is inside the grid (0 ≤ x,y ≤ 5). Valid → dispatch → square moves. Audience: just watch the green square trace a path.',
      watch:      'Four successful move calls. Status row shows green DCP ✓ each time.',
      expected:   'Square ends up where the LLM planned.',
    },
    steps: [
      { kind: 'view', view: 'grid' },
      { kind: 'set_status', text: '[2/3] LLM MOVES THE SQUARE' },
      { kind: 'pos', x: 0, y: 0 },
      { kind: 'clear_narration' },
      { kind: 'narrate', line: 0, role: 'user', text: 'USER: walk a small loop' },
      wait(1500),

      { kind: 'narrate', line: 1, role: 'llm',     text: 'LLM→ move(right, 3)' },
      { kind: 'narrate', line: 2, role: 'dcp_req', text: 'DCP… validating' },
      wait(700),
      { kind: 'narrate', line: 2, role: 'dcp_ok',  text: 'DCP ✓ in bounds — go' },
      { kind: 'move', dx: 3, dy: 0 },
      wait(1500),

      { kind: 'narrate', line: 1, role: 'llm',     text: 'LLM→ move(down, 2)' },
      { kind: 'narrate', line: 2, role: 'dcp_req', text: 'DCP… validating' },
      wait(700),
      { kind: 'narrate', line: 2, role: 'dcp_ok',  text: 'DCP ✓ in bounds — go' },
      { kind: 'move', dx: 0, dy: 2 },
      wait(1500),

      { kind: 'narrate', line: 1, role: 'llm',     text: 'LLM→ move(left, 2)' },
      { kind: 'narrate', line: 2, role: 'dcp_req', text: 'DCP… validating' },
      wait(700),
      { kind: 'narrate', line: 2, role: 'dcp_ok',  text: 'DCP ✓ in bounds — go' },
      { kind: 'move', dx: -2, dy: 0 },
      wait(1500),

      { kind: 'narrate', line: 1, role: 'llm',     text: 'LLM→ move(up, 1)' },
      { kind: 'narrate', line: 2, role: 'dcp_req', text: 'DCP… validating' },
      wait(700),
      { kind: 'narrate', line: 2, role: 'dcp_ok',  text: 'DCP ✓ in bounds — go' },
      { kind: 'move', dx: 0, dy: -1 },
      wait(2500),
    ],
  },

  // ────────────────────────────────────────────────────────────────
  {
    tag: '[3/3] DCP STOPS A BAD MOVE',
    description: 'LLM tries to leave the grid; bridge rejects; square stays',
    briefing: {
      testing:    'The LLM is told to "move right 5". The square is at column 1; column 1 + 5 = 6, which is OFF the grid (valid cols are 0–5).',
      mechanism:  'The manifest declares: after the move, x must stay in [0,5]. The bridge computes the would-be position, finds it out of range, returns DCP ✗ — the move call is NEVER dispatched. The square does not move. The grid flashes red. The dashed red ✗ marks where the LLM tried to go.',
      watch:      'Square sits still. Grid border flashes red. A red dashed ghost cell appears at the out-of-bounds target. Status row shows red DCP ✗.',
      expected:   'No actuation. Without DCP, a hallucinated argument would have moved hardware into an invalid state.',
    },
    steps: [
      { kind: 'view', view: 'grid' },
      { kind: 'set_status', text: '[3/3] DCP STOPS A BAD MOVE' },
      { kind: 'pos', x: 1, y: 2 },
      { kind: 'clear_narration' },
      { kind: 'narrate', line: 0, role: 'user', text: 'USER: keep going right' },
      wait(1500),

      // First — a legal move, just to set the scene
      { kind: 'narrate', line: 1, role: 'llm',     text: 'LLM→ move(right, 3)' },
      { kind: 'narrate', line: 2, role: 'dcp_req', text: 'DCP… validating' },
      wait(700),
      { kind: 'narrate', line: 2, role: 'dcp_ok',  text: 'DCP ✓ in bounds — go' },
      { kind: 'move', dx: 3, dy: 0 },
      wait(1800),

      // Now the bad one
      { kind: 'narrate', line: 0, role: 'user', text: 'USER: now move right 5 more' },
      wait(1200),
      { kind: 'narrate', line: 1, role: 'llm',     text: 'LLM→ move(right, 5)' },
      { kind: 'narrate', line: 2, role: 'dcp_req', text: 'DCP… validating' },
      wait(900),
      // The "would-be" position would be x=4+5=9, but cap at column 6 as the visible ghost
      { kind: 'ghost', x: 6, y: 2 },
      { kind: 'flash', flash: 'err' },
      { kind: 'narrate', line: 2, role: 'dcp_err', text: 'DCP ✗ out of bounds (x=9)' },
      wait(2500),
      { kind: 'flash', flash: '' },
      { kind: 'ghost', clear: true },
      wait(800),

      // LLM self-corrects
      { kind: 'narrate', line: 1, role: 'llm',     text: 'LLM→ move(right, 1)' },
      { kind: 'narrate', line: 2, role: 'dcp_req', text: 'DCP… validating' },
      wait(700),
      { kind: 'narrate', line: 2, role: 'dcp_ok',  text: 'DCP ✓ in bounds — go' },
      { kind: 'move', dx: 1, dy: 0 },
      wait(3000),
    ],
  },
];
