const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const fs = require("fs");
const path = require("path");
const D = __dirname;
let applyTheme = null;
try { applyTheme = require(path.join(process.env.PPTX_SKILL_DIR || "", "scripts", "apply_theme.js")).applyTheme; }
catch (e) { console.warn("NOTE: apply_theme.js not found (set PPTX_SKILL_DIR). Theme colors will not be applied; ask Claude Code to run the pptx skill's applyTheme step."); }

const THEME = {
  name: "Selfmade Signal",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "10242E", lt1: "FFFFFF", dk2: "0B2B3A", lt2: "EEF3F6",
    accent1: "1F8A9E", accent2: "FF7A1A", accent3: "2FA37C", accent4: "D9534F",
    accent5: "6C7A89", accent6: "F2B134", hlink: "1F8A9E", folHlink: "6C7A89",
  },
};
const HEX = { teal: "1F8A9E", orange: "FF7A1A", green: "2FA37C", red: "D9534F", slate: "6C7A89", ink: "0B2B3A", white: "FFFFFF", mist: "EEF3F6", amber: "F2B134", text: "10242E" };

async function icon(name, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(fa[name], { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = "Selfmade Reader - UHF RFID over Ethernet";
  pres.author = "C2A-2796";
  const C = pres.SchemeColor;
  const W = 13.333, M = 0.6, CW = W - 2 * M;

  // ---------- layouts ----------
  pres.defineSlideMaster({
    title: "TITLE_DARK",
    objects: [{ rect: { x: 0, y: 0, w: W, h: 7.5, fill: { color: C.text2 } } }],
    slideNumber: undefined,
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: "FFFFFF" },
    objects: [
      { text: { text: "Selfmade Reader", options: { x: M, y: 7.0, w: 4, h: 0.3, fontSize: 11, color: C.accent5, margin: 0, isTextBox: true } } },
      {
        placeholder: {
          options: { name: "title", type: "title", x: M, y: 0.45, w: CW, h: 0.9, fontSize: 34, bold: true, color: C.text2, align: "left", valign: "middle", margin: 0 },
          text: "",
        },
      },
    ],
    slideNumber: { x: W - M - 0.6, y: 7.0, w: 0.6, h: 0.3, fontSize: 11, color: C.accent5, align: "right" },
  });
  pres.defineSlideMaster({
    title: "DARK_CONTENT",
    objects: [
      { rect: { x: 0, y: 0, w: W, h: 7.5, fill: { color: C.text2 } } },
      {
        placeholder: {
          options: { name: "title", type: "title", x: M, y: 0.6, w: CW, h: 0.9, fontSize: 36, bold: true, color: C.background1, align: "left", valign: "middle", margin: 0 },
          text: "",
        },
      },
    ],
  });

  const T = (s, text, opts) => s.addText(text, Object.assign({ isTextBox: true, margin: 0, color: C.text1, fontSize: 16, valign: "top" }, opts));
  const card = (s, x, y, w, h, fill, name) =>
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: C.background2, width: 0.75 }, objectName: name });
  const ring = async (s, x, y, d, fill, iconName, iconColor = HEX.white, name) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill, width: 0 }, objectName: (name || iconName) + " circle" });
    const p = d * 0.5;
    s.addImage({ data: await icon(iconName, iconColor), x: x + (d - p) / 2, y: y + (d - p) / 2, w: p, h: p, altText: iconName.replace(/^Fa/, "") + " icon" });
  };
  const arrow = (s, x1, y, x2, color = HEX.slate) =>
    s.addShape(pres.shapes.LINE, { x: x1, y, w: x2 - x1, h: 0, line: { color, width: 2.25, endArrowType: "triangle" }, objectName: "arrow" });
  const shot = (s, file, x, y, w, h, alt) => {
    s.addShape(pres.shapes.RECTANGLE, { x: x - 0.04, y: y - 0.04, w: w + 0.08, h: h + 0.08, fill: { color: C.background1 }, line: { color: C.background2, width: 1.25 }, shadow: { type: "outer", color: "000000", blur: 8, offset: 2, angle: 90, opacity: 0.18 }, objectName: "screenshot frame" });
    s.addImage({ path: file, x, y, w, h, altText: alt });
  };
  const note = (s, text) => s.addNotes(text);

  // =============== 1. Title ===============
  pres.addSection({ title: "Intro" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Intro" });
  T(s, "Selfmade Reader", { x: 0.8, y: 2.1, w: 7.6, h: 1.2, fontSize: 54, bold: true, color: C.background1, fontFace: "Cambria", valign: "middle", objectName: "Title" });
  T(s, "UHF RFID tags to your computer over Ethernet", { x: 0.8, y: 3.4, w: 7.9, h: 0.95, fontSize: 24, color: C.background2, objectName: "Subtitle" });
  T(s, "Configure  ·  Monitor  ·  Store  ·  Forward", { x: 0.8, y: 4.7, w: 7.4, h: 0.5, fontSize: 20, bold: true, color: C.accent2, objectName: "Tagline" });
  T(s, "Demo and walkthrough", { x: 0.8, y: 6.5, w: 5, h: 0.4, fontSize: 14, color: C.accent5, objectName: "Context" });
  // vertical chain: tag -> reader -> computer
  const cx = 9.35;
  await ring(s, cx, 1.35, 1.15, HEX.orange, "FaTag", HEX.white, "tag");
  await ring(s, cx, 3.2, 1.15, HEX.teal, "FaBroadcastTower", HEX.white, "reader");
  await ring(s, cx, 5.05, 1.15, HEX.white, "FaLaptop", HEX.ink, "computer");
  s.addShape(pres.shapes.LINE, { x: cx + 0.575, y: 2.55, w: 0, h: 0.6, line: { color: HEX.slate, width: 2.25, endArrowType: "triangle" } });
  s.addShape(pres.shapes.LINE, { x: cx + 0.575, y: 4.4, w: 0, h: 0.6, line: { color: HEX.slate, width: 2.25, endArrowType: "triangle" } });
  T(s, "UHF tag", { x: cx + 1.4, y: 1.72, w: 2.4, h: 0.4, fontSize: 18, color: C.background1, objectName: "label tag" });
  T(s, "Reader", { x: cx + 1.4, y: 3.57, w: 2.4, h: 0.4, fontSize: 18, color: C.background1, objectName: "label reader" });
  T(s, "Your computer", { x: cx + 1.4, y: 5.42, w: 2.4, h: 0.4, fontSize: 18, color: C.background1, objectName: "label computer" });
  note(s, "Welcome. This is Selfmade Reader: a small program that takes the tags a UHF RFID reader sees, and gets them onto a computer over a normal Ethernet cable. It lets you configure the reader from a web page, watch tags live, store them in a CSV file and forward them to the internet. In the next 15-20 minutes I will explain the problem we solved, how it works, show it live, and then say exactly what is tested and what is not.");

  // =============== 2. Problem ===============
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Intro" });
  s.addText("The reader beeped, but no data arrived", { placeholder: "title" });
  T(s, [
    { text: "A UHF reader was cabled over Ethernet and beeped on every tag it read.", options: { bullet: true, breakLine: true, paraSpaceAfter: 14 } },
    { text: "The computer could see the reader on the network, yet received 0 bytes of tag data.", options: { bullet: true, breakLine: true, paraSpaceAfter: 14 } },
    { text: "Guessing protocols failed. The manufacturer's own logs and software showed how it really works.", options: { bullet: true } },
  ], { x: M, y: 1.9, w: 5.9, h: 3.8, fontSize: 20, objectName: "Problem points" });
  card(s, 7.0, 1.8, 5.7, 2.0, HEX.mist, "ok card");
  await ring(s, 7.3, 2.15, 1.0, HEX.green, "FaCheck", HEX.white, "ok");
  T(s, "Radio side works", { x: 8.6, y: 2.1, w: 4.0, h: 0.5, fontSize: 22, bold: true, color: C.text2, objectName: "ok title" });
  T(s, "The reader beeps on every tag.", { x: 8.6, y: 2.7, w: 3.9, h: 0.8, fontSize: 16, objectName: "ok text" });
  card(s, 7.0, 4.1, 5.7, 2.0, HEX.mist, "bad card");
  await ring(s, 7.3, 4.45, 1.0, HEX.red, "FaTimes", HEX.white, "bad");
  T(s, "Ethernet side silent", { x: 8.6, y: 4.4, w: 4.0, h: 0.5, fontSize: 22, bold: true, color: C.text2, objectName: "bad title" });
  T(s, "0 bytes of tag data reached the computer.", { x: 8.6, y: 5.0, w: 3.9, h: 0.8, fontSize: 16, objectName: "bad text" });
  note(s, "When we started, the reader worked: it beeped on every tag. But over Ethernet nothing arrived. We tried the common reader protocols, a packet capture and listeners on many ports, and always got silence. The breakthrough was reading the manufacturer's own logs, which showed the real message format and the real settings.");

  // =============== 3. Root cause ===============
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Intro" });
  s.addText("Root cause: tags left through the wrong port", { placeholder: "title" });
  const colW = 5.5, ly = 1.8, lh = 4.0;
  card(s, M, ly, colW, lh, "FBE9E8", "before card");
  card(s, W - M - colW, ly, colW, lh, "E5F4EE", "after card");
  T(s, "BEFORE", { x: M + 0.35, y: ly + 0.3, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.accent4, objectName: "before label" });
  T(s, "AFTER", { x: W - M - colW + 0.35, y: ly + 0.3, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.accent3, objectName: "after label" });
  const rowsBA = [
    ["Output interface", "RS232 / RS485 (serial)", "RJ45 (Ethernet)"],
    ["Remote server", "120.78.148.145 : 0", "192.168.1.10 : 6000"],
    ["Result", "Tags never leave the serial cable", "Reader connects to the PC and pushes every tag"],
  ];
  rowsBA.forEach((r, i) => {
    const y = ly + 0.9 + i * 1.0;
    T(s, r[0], { x: M + 0.35, y, w: 4.8, h: 0.3, fontSize: 14, color: C.accent5, objectName: "before key " + i });
    T(s, r[1], { x: M + 0.35, y: y + 0.3, w: 4.8, h: 0.55, fontSize: 18, bold: true, objectName: "before val " + i });
    T(s, r[0], { x: W - M - colW + 0.35, y, w: 4.8, h: 0.3, fontSize: 14, color: C.accent5, objectName: "after key " + i });
    T(s, r[2], { x: W - M - colW + 0.35, y: y + 0.3, w: 4.8, h: 0.55, fontSize: 18, bold: true, objectName: "after val " + i });
  });
  await ring(s, W / 2 - 0.4, ly + lh / 2 - 0.4, 0.8, HEX.orange, "FaArrowRight", HEX.white, "to");
  T(s, "Keep the reader in Active mode. Never use Answer mode: it silences the buzzer and stops pushing tags.", { x: M, y: 6.1, w: CW, h: 0.6, fontSize: 16, color: C.text2, bold: true, objectName: "Warning" });
  note(s, "The cause was a setting, not a cable or a bug. The reader had its Interface set to RS232/RS485, so it pushed tags out of its serial port. The Ethernet port was only used for settings. Its remote server was still the factory default. We switched the Interface to RJ45 and pointed the remote server at the computer. One warning for everyone: do not set Work mode to Answer; the reader then stops pushing and the buzzer goes silent.");

  // =============== 4. Architecture ===============
  pres.addSection({ title: "How it works" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "How it works" });
  s.addText("How it works", { placeholder: "title" });
  const nodeW = 2.1, gap = 1.2, ny = 2.0, nh = 1.75;
  const nx = (i) => M + i * (nodeW + gap);
  const nodes = [
    ["FaTag", HEX.orange, "UHF tag", "EPC Gen2 tag, read at 865-868 MHz"],
    ["FaBroadcastTower", HEX.teal, "Reader", "SN5300 / CF5300 type, pushes each read"],
    ["FaLaptop", HEX.ink, "Selfmade Reader", "Listens on port 6000, shows and stores tags"],
  ];
  for (let i = 0; i < 3; i++) {
    card(s, nx(i), ny, nodeW, nh, HEX.mist, "node " + i);
    await ring(s, nx(i) + nodeW / 2 - 0.45, ny + 0.18, 0.9, nodes[i][1], nodes[i][0], HEX.white, "node icon " + i);
    T(s, nodes[i][2], { x: nx(i), y: ny + 1.2, w: nodeW, h: 0.45, fontSize: 17, bold: true, align: "center", color: C.text2, objectName: "node title " + i });
    T(s, nodes[i][3], { x: nx(i) + 0.1, y: ny + nh + 0.2, w: nodeW - 0.2, h: 1.0, fontSize: 15, align: "center", color: C.text1, objectName: "node text " + i });
  }
  // outputs
  const ox = nx(3);
  const outs = [["FaFileCsv", "CSV file"], ["FaGlobe", "HTTP webhook"], ["FaCloud", "MQTT broker"], ["FaServer", "TCP server"]];
  for (let i = 0; i < 4; i++) {
    const y = ny - 0.35 + i * 0.72;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ox, y, w: nodeW, h: 0.6, rectRadius: 0.1, fill: { color: HEX.mist }, line: { color: C.background2, width: 0.75 }, objectName: "output " + i });
    s.addImage({ data: await icon(outs[i][0], HEX.teal), x: ox + 0.15, y: y + 0.14, w: 0.32, h: 0.32, altText: outs[i][1] + " icon" });
    T(s, outs[i][1], { x: ox + 0.65, y: y + 0.1, w: nodeW - 0.7, h: 0.4, fontSize: 14, valign: "middle", objectName: "output text " + i });
  }
  T(s, "Outputs", { x: ox, y: ny + 2.65, w: nodeW, h: 0.4, fontSize: 18, bold: true, align: "center", color: C.text2, objectName: "outputs title" });
  T(s, "Saved and sent over any network", { x: ox, y: ny + 3.05, w: nodeW, h: 0.9, fontSize: 13, align: "center", objectName: "outputs text" });
  // arrows with labels
  const lab = ["868 MHz", "Ethernet", "save, send"];
  for (let i = 0; i < 3; i++) {
    arrow(s, nx(i) + nodeW + 0.08, ny + nh / 2, nx(i + 1) - 0.08);
    T(s, lab[i], { x: nx(i) + nodeW, y: ny + nh / 2 - 0.5, w: gap, h: 0.4, fontSize: 13, align: "center", color: C.accent5, objectName: "arrow label " + i });
  }
  T(s, "Tags go straight from the reader to your computer: no cloud and no vendor software needed.", { x: M, y: 6.25, w: CW, h: 0.6, fontSize: 18, bold: true, color: C.text2, objectName: "Architecture takeaway" });
  note(s, "Left to right: a UHF tag is read by the reader over 868 MHz radio. The reader is set to RJ45, so it opens a TCP connection to the computer, on port 6000, and pushes every tag it reads. Selfmade Reader receives it, shows it live, writes it to a CSV file and can forward each read to an HTTP address, an MQTT broker or a TCP server, using whatever network the computer has: Ethernet, WiFi or a 4G/5G hotspot.");

  // =============== 5. Two connections ===============
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "How it works" });
  s.addText("Two connections, two jobs", { placeholder: "title" });
  const cw2 = 5.85;
  card(s, M, 1.7, cw2, 2.75, HEX.mist, "cmd card");
  await ring(s, M + 0.3, 1.95, 0.8, HEX.teal, "FaSlidersH", HEX.white, "cmd");
  T(s, "Settings", { x: M + 1.3, y: 1.95, w: 4.3, h: 0.4, fontSize: 22, bold: true, color: C.text2, objectName: "cmd title" });
  T(s, "PC to reader  ·  TCP 60000", { x: M + 1.3, y: 2.4, w: 4.4, h: 0.4, fontSize: 16, color: C.accent1, bold: true, objectName: "cmd sub" });
  T(s, "Read and write the reader's settings, restart it. A backup is saved before every change.", { x: M + 0.3, y: 3.2, w: cw2 - 0.6, h: 1.0, fontSize: 16, objectName: "cmd text" });
  card(s, W - M - cw2, 1.7, cw2, 2.75, HEX.mist, "push card");
  await ring(s, W - M - cw2 + 0.3, 1.95, 0.8, HEX.orange, "FaBolt", HEX.white, "push");
  T(s, "Tag data", { x: W - M - cw2 + 1.3, y: 1.95, w: 4.3, h: 0.4, fontSize: 22, bold: true, color: C.text2, objectName: "push title" });
  T(s, "Reader to PC  ·  TCP 6000", { x: W - M - cw2 + 1.3, y: 2.4, w: 4.4, h: 0.4, fontSize: 16, color: C.accent2, bold: true, objectName: "push sub" });
  T(s, "The reader connects to the computer and pushes every tag: EPC, signal strength (RSSI) and antenna.", { x: W - M - cw2 + 0.3, y: 3.2, w: cw2 - 0.6, h: 1.0, fontSize: 16, objectName: "push text" });
  T(s, "What one pushed tag message looks like", { x: M, y: 4.85, w: CW, h: 0.35, fontSize: 14, color: C.accent5, objectName: "frame caption" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 5.25, w: CW, h: 1.25, rectRadius: 0.1, fill: { color: C.text2 }, line: { color: C.text2, width: 0 }, objectName: "frame box" });
  T(s, "43 54 00 1c 01 45 01 c3 9b 24 03 14 45 2c 01 0f 01 01 30 08 33 b2 dd d9 01 40 00 00 00 00 3c 9a", { x: M + 0.3, y: 5.4, w: CW - 0.6, h: 0.45, fontSize: 13, fontFace: "Courier New", color: C.background2, objectName: "frame hex" });
  T(s, [{ text: "decodes to   EPC ", options: { color: C.background2 } }, { text: "300833B2DDD9014000000000", options: { color: C.accent2, bold: true, fontFace: "Courier New" } }, { text: "   RSSI 60   antenna 1", options: { color: C.background2 } }], { x: M + 0.3, y: 5.9, w: CW - 0.6, h: 0.45, fontSize: 16, objectName: "frame decode" });
  note(s, "There are two separate connections. Port 60000 lives on the reader: the computer uses it to read and change settings. Port 6000 lives on the computer: the reader connects to it and pushes tags. The box at the bottom is a real message captured from the reader; it decodes to a 12-byte EPC, the signal strength and the antenna number.");

  // =============== 6. Demo steps ===============
  pres.addSection({ title: "Demo" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Demo" });
  s.addText("Demo: five steps", { placeholder: "title" });
  const steps = [
    ["FaPlay", HEX.teal, "Start", "python3\nselfmade_reader.py"],
    ["FaSearch", HEX.teal, "Find", "Reader setup, then Find readers"],
    ["FaBolt", HEX.orange, "Set up", "One-click Ethernet setup"],
    ["FaVolumeUp", HEX.green, "Read", "Hold a tag: it beeps and appears"],
    ["FaFileCsv", HEX.ink, "Use", "Open the CSV or forward it"],
  ];
  const sw = 2.3, sg = 0.15;
  for (let i = 0; i < 5; i++) {
    const x = M + i * (sw + sg);
    card(s, x, 1.9, sw, 3.5, HEX.mist, "step card " + i);
    await ring(s, x + sw / 2 - 0.45, 2.15, 0.9, steps[i][1], steps[i][0], HEX.white, "step icon " + i);
    T(s, String(i + 1), { x: x + 0.15, y: 2.05, w: 0.5, h: 0.5, fontSize: 24, bold: true, color: C.accent5, fontFace: "Cambria", objectName: "step number " + i });
    T(s, steps[i][2], { x, y: 3.3, w: sw, h: 0.5, fontSize: 24, bold: true, align: "center", color: C.text2, fontFace: "Cambria", objectName: "step title " + i });
    T(s, steps[i][3], { x: x + 0.1, y: 3.95, w: sw - 0.2, h: 1.2, fontSize: 15, align: "center", objectName: "step text " + i });
  }
  T(s, "Needs only Python 3.8+ and one file. The computer needs an address in the reader's network, for example 192.168.1.20.", { x: M, y: 5.9, w: CW, h: 0.7, fontSize: 16, color: C.text2, objectName: "demo footnote" });
  note(s, "This is the whole demo. One: start the program. Two: open the Reader setup tab and click Find readers on the network. Three: click One-click Ethernet setup; it saves a backup, sets the interface to RJ45, points the reader at this computer and restarts it. Four: hold a tag near the antenna; the reader beeps and the tag appears. Five: open the CSV, or switch on forwarding. The next three slides show the screens.");

  // =============== 7. Dashboard ===============
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Demo" });
  s.addText("Screen 1: live dashboard", { placeholder: "title" });
  shot(s, path.join(D, "img", "dash.png"), M, 1.75, 7.9, 7.9 * 370 / 1140, "Dashboard with counters and live tag table");
  T(s, "Recorded reads replayed for the demo", { x: M, y: 1.75 + 7.9 * 370 / 1140 + 0.15, w: 7.9, h: 0.3, fontSize: 12, color: C.accent5, objectName: "caption dash" });
  T(s, "The top bar tells you the state at a glance", { x: M, y: 4.75, w: 7.9, h: 0.4, fontSize: 18, bold: true, color: C.text2, objectName: "bar heading" });
  const pills = [["reader connected", HEX.green, "E5F4EE"], ["reachable, not sending", "A15C07", "FBF0DC"], ["not reachable", HEX.red, "FBE9E8"]];
  pills.forEach((p, i) => {
    const x = M + i * 2.7;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.3, w: 2.55, h: 0.5, rectRadius: 0.25, fill: { color: p[2] }, line: { color: p[2], width: 0 }, objectName: "status pill " + i });
    T(s, p[0], { x, y: 5.3, w: 2.55, h: 0.5, fontSize: 14, bold: true, color: p[1], align: "center", valign: "middle", objectName: "status text " + i });
  });
  T(s, "Not reachable: check cable, power and IP. Reachable but not sending: run One-click setup.", { x: M, y: 5.95, w: 7.9, h: 0.7, fontSize: 14, objectName: "status help" });
  const callouts = [
    ["FaTachometerAlt", HEX.teal, "Counters", "Reads, unique tags, CSV rows, forwarded OK and failed"],
    ["FaListUl", HEX.orange, "Live table", "EPC, reads, RSSI, antenna and last seen, updating as tags arrive"],
    ["FaDownload", HEX.ink, "Export", "Download the CSV or clear the list in one click"],
  ];
  for (let i = 0; i < 3; i++) {
    const y = 1.75 + i * 1.55;
    await ring(s, 9.0, y, 0.7, callouts[i][1], callouts[i][0], HEX.white, "callout " + i);
    T(s, callouts[i][2], { x: 9.9, y: y - 0.02, w: 2.85, h: 0.4, fontSize: 18, bold: true, color: C.text2, objectName: "callout title " + i });
    T(s, callouts[i][3], { x: 9.9, y: y + 0.4, w: 2.85, h: 0.95, fontSize: 14, objectName: "callout text " + i });
  }
  note(s, "Screen one is the dashboard. The pill at the top is the most useful part: green means the reader is connected and pushing; amber means the reader answers but is not sending, so run One-click setup; red means the computer cannot reach the reader at all, so check cable, power and IP. Below it, the counters and the live table. This screenshot uses recorded reads from our reader, replayed so we can show it without a live tag.");

  // =============== 8. Setup ===============
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Demo" });
  s.addText("Screen 2: reader setup", { placeholder: "title" });
  shot(s, path.join(D, "img", "setup.png"), M, 1.75, 7.9, 7.9 * 565 / 1140, "Reader setup page with quick setup and reader settings");
  T(s, "Settings read from recorded reader data", { x: M, y: 1.75 + 7.9 * 565 / 1140 + 0.15, w: 7.9, h: 0.3, fontSize: 12, color: C.accent5, objectName: "caption setup" });
  const sc = [
    ["FaBolt", HEX.orange, "One-click setup", "Interface to RJ45, remote server to this computer, then restart"],
    ["FaSave", HEX.teal, "Backup first", "Every write saves the old settings to a backup file you can restore"],
    ["FaWifi", HEX.ink, "WiFi and network", "Reader IP, remote server, WiFi name and password in one place"],
  ];
  for (let i = 0; i < 3; i++) {
    const y = 1.75 + i * 1.55;
    await ring(s, 9.0, y, 0.7, sc[i][1], sc[i][0], HEX.white, "callout " + i);
    T(s, sc[i][2], { x: 9.9, y: y - 0.02, w: 2.85, h: 0.4, fontSize: 18, bold: true, color: C.text2, objectName: "callout title " + i });
    T(s, sc[i][3], { x: 9.9, y: y + 0.4, w: 2.85, h: 0.95, fontSize: 14, objectName: "callout text " + i });
  }
  note(s, "Screen two is where you configure the reader. The big blue button runs the whole fix in one go. Underneath are the individual settings: output interface, work mode, RF power, the network block with the remote server, and WiFi. Before any write the program saves the reader's current settings into a backup folder, and there is a Restore button. WiFi and the 4G interface are present in the form but are not yet tested on our reader.");

  // =============== 9. Data & forwarding ===============
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Demo" });
  s.addText("Screen 3: data and forwarding", { placeholder: "title" });
  const dh = 4.75, dw = dh * 1140 / 825;
  shot(s, path.join(D, "img", "data.png"), M, 1.75, dw, dh, "Data and forwarding page");
  const dc = [
    ["FaFileCsv", HEX.teal, "Storage", "CSV path, one row per tag per 1, 5 or 60 seconds, optional daily files"],
    ["FaCloudUploadAlt", HEX.orange, "Forwarding", "HTTP webhook, MQTT broker or TCP server, each with a Test button"],
    ["FaLock", HEX.ink, "Credentials", "Kept in a local settings file that is never committed to GitHub"],
  ];
  for (let i = 0; i < 3; i++) {
    const y = 1.75 + i * 1.55;
    await ring(s, 7.75, y, 0.7, dc[i][1], dc[i][0], HEX.white, "callout " + i);
    T(s, dc[i][2], { x: 8.65, y: y - 0.02, w: 4.1, h: 0.4, fontSize: 18, bold: true, color: C.text2, objectName: "callout title " + i });
    T(s, dc[i][3], { x: 8.65, y: y + 0.4, w: 4.1, h: 0.95, fontSize: 14, objectName: "callout text " + i });
  }
  note(s, "Screen three is storage and forwarding. Tags are written to a CSV file; by default one row per tag per second so the file stays small, or every read, or one file per day. Below, you can forward every read to an HTTP address, an MQTT broker or a TCP server. Each has a Test button. This uses the computer's own connection, so WiFi or a 4G/5G phone hotspot works.");

  // =============== 10. Where data goes ===============
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Demo" });
  s.addText("Where the data goes", { placeholder: "title" });
  const hdr = (t) => ({ text: t, options: { bold: true, color: HEX.white, fill: { color: HEX.ink }, fontSize: 14, align: "left", valign: "middle" } });
  const rows = JSON.parse(fs.readFileSync(path.join(D, "rows.json"))).sort((a, b) => a[0].localeCompare(b[0]));
  const trows = [[hdr("timestamp"), hdr("epc"), hdr("rssi"), hdr("ant")]].concat(
    rows.map((r, i) => r.map((c, j) => ({ text: c, options: { fontSize: 13, fontFace: j === 1 ? "Courier New" : "Calibri", color: HEX.text, fill: { color: i % 2 ? HEX.white : HEX.mist }, valign: "middle" } })))
  );
  T(s, "Real rows from our reader's CSV", { x: M, y: 1.65, w: 7.3, h: 0.35, fontSize: 16, bold: true, color: C.text2, objectName: "csv heading" });
  s.addTable(trows, { x: M, y: 2.1, w: 7.3, colW: [2.65, 3.1, 0.75, 0.8], rowH: 0.46, border: { type: "solid", pt: 0.5, color: "D5DDE3" }, objectName: "CSV sample table" });
  T(s, "One row per tag per second by default; every read if you prefer.", { x: M, y: 5.35, w: 7.3, h: 0.6, fontSize: 14, color: C.accent5, objectName: "csv note" });
  // forwarding flow
  const fx = 8.4, fw = 4.33;
  const flow = [
    ["FaTag", HEX.orange, "Tag read", "Saved to CSV first, always"],
    ["FaCloudUploadAlt", HEX.teal, "Send", "HTTP, MQTT or TCP"],
    ["FaHdd", HEX.amber, "Link down?", "Saved to a spool file on disk"],
    ["FaSyncAlt", HEX.green, "Auto-resend", "Every 30 seconds, oldest first"],
  ];
  for (let i = 0; i < 4; i++) {
    const y = 1.7 + i * 1.28;
    card(s, fx, y, fw, 1.0, HEX.mist, "flow card " + i);
    await ring(s, fx + 0.2, y + 0.18, 0.64, flow[i][1], flow[i][0], i === 2 ? HEX.ink : HEX.white, "flow icon " + i);
    T(s, flow[i][2], { x: fx + 1.05, y: y + 0.12, w: fw - 1.2, h: 0.38, fontSize: 16, bold: true, color: C.text2, objectName: "flow title " + i });
    T(s, flow[i][3], { x: fx + 1.05, y: y + 0.52, w: fw - 1.2, h: 0.4, fontSize: 14, objectName: "flow text " + i });
    if (i < 3) s.addShape(pres.shapes.LINE, { x: fx + fw / 2, y: y + 1.0, w: 0, h: 0.28, line: { color: HEX.slate, width: 2, endArrowType: "triangle" } });
  }
  note(s, "On the left, real rows from our reader's CSV: timestamp, the 12-byte EPC, signal strength and antenna. On the right, what happens to each read. It is always saved to CSV first. If forwarding is on it is sent; if the network or the server is down, the item is saved in a spool file on disk and resent automatically every 30 seconds, oldest first. We tested that with a server that was down and then came back.");

  // =============== 11. Run anywhere ===============
  pres.addSection({ title: "Deploy" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Deploy" });
  s.addText("Run it on any computer", { placeholder: "title" });
  const os = [
    ["FaWindows", "Windows", "START_WINDOWS.bat", "Task Scheduler task at logon"],
    ["FaApple", "macOS", "START_MAC.command", "launchd agent at login"],
    ["FaLinux", "Linux", "./START_LINUX.sh", "systemd service, also at boot"],
  ];
  const ow = 3.85, og = 0.29;
  for (let i = 0; i < 3; i++) {
    const x = M + i * (ow + og);
    card(s, x, 1.7, ow, 3.55, HEX.mist, "os card " + i);
    await ring(s, x + 0.3, 1.95, 0.85, HEX.ink, os[i][0], HEX.white, "os icon " + i);
    T(s, os[i][1], { x: x + 1.35, y: 2.05, w: ow - 1.5, h: 0.6, fontSize: 24, bold: true, color: C.text2, fontFace: "Cambria", valign: "middle", objectName: "os title " + i });
    T(s, "Start", { x: x + 0.3, y: 3.05, w: ow - 0.6, h: 0.3, fontSize: 14, color: C.accent5, objectName: "start label " + i });
    T(s, os[i][2], { x: x + 0.3, y: 3.35, w: ow - 0.6, h: 0.4, fontSize: 16, bold: true, fontFace: "Courier New", objectName: "start cmd " + i });
    T(s, "Auto-start", { x: x + 0.3, y: 4.0, w: ow - 0.6, h: 0.3, fontSize: 14, color: C.accent5, objectName: "auto label " + i });
    T(s, os[i][3], { x: x + 0.3, y: 4.3, w: ow - 0.6, h: 0.6, fontSize: 16, objectName: "auto text " + i });
  }
  T(s, [
    { text: "Needs only Python 3.8+ and one file. ", options: { bold: true, color: HEX.ink } },
    { text: "No packages to install. Give the computer an address on the reader's network, for example 192.168.1.20 with no gateway, then use the one-click setup." },
  ], { x: M, y: 5.6, w: CW, h: 0.9, fontSize: 18, objectName: "requirements" });
  note(s, "To run it anywhere you need Python 3.8 or newer and the one file. There are double-click launchers for Windows, macOS and Linux, and a single command, --install-autostart, that makes it start by itself: a systemd service on Linux, a launch agent on macOS, a scheduled task on Windows. Important honesty: only the Linux version has been tested so far.");

  // =============== 12. Hardening ===============
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Deploy" });
  s.addText("Built for deployment", { placeholder: "title" });
  const hard = [
    ["FaTrafficLight", HEX.green, "Clear status", "Green, amber or red bar tells you what to check"],
    ["FaHeartbeat", HEX.red, "Health URL", "/api/health returns 200 when a reader is pushing, else 503"],
    ["FaLock", HEX.ink, "Password", "Optional password for the web page"],
    ["FaShieldAlt", HEX.teal, "Reader allow-list", "Only chosen reader IPs may send tags"],
    ["FaRedo", HEX.orange, "Self-recovery", "Restarts after a crash; started on 3 reboots in a row"],
    ["FaSave", HEX.slate, "Backup and restore", "Reader settings backed up before every change"],
  ];
  const hw = 3.85, hg = 0.29, hh = 2.1;
  for (let i = 0; i < 6; i++) {
    const x = M + (i % 3) * (hw + hg), y = 1.7 + Math.floor(i / 3) * (hh + 0.3);
    card(s, x, y, hw, hh, HEX.mist, "hard card " + i);
    await ring(s, x + 0.3, y + 0.3, 0.75, hard[i][1], hard[i][0], HEX.white, "hard icon " + i);
    T(s, hard[i][2], { x: x + 1.25, y: y + 0.38, w: hw - 1.4, h: 0.6, fontSize: 18, bold: true, color: C.text2, valign: "middle", objectName: "hard title " + i });
    T(s, hard[i][3], { x: x + 0.3, y: y + 1.2, w: hw - 0.6, h: 0.8, fontSize: 14, objectName: "hard text " + i });
  }
  note(s, "These are the features added for real deployment. A clear status bar. A health URL a monitoring tool can poll. An optional password for the web page and an allow-list of reader IPs, because anyone who can open the page can change reader settings. It restarts after a crash, and on our test computer it started by itself after three reboots. And the reader's settings are backed up before every change. When we looked at the machine after a few days, it had also shown us a real-world failure: the Ethernet port was down, so no data came, and the status bar would now say so in red.");

  // =============== 13. Verified vs not ===============
  pres.addSection({ title: "Status" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Status" });
  s.addText("What is tested, and what is not yet", { placeholder: "title" });
  const half = 5.9;
  card(s, M, 1.65, half, 4.95, "E5F4EE", "tested card");
  card(s, W - M - half, 1.65, half, 4.95, "FBF0DC", "untested card");
  await ring(s, M + 0.3, 1.9, 0.6, HEX.green, "FaCheck", HEX.white, "tested");
  T(s, "Tested", { x: M + 1.1, y: 1.95, w: 4, h: 0.5, fontSize: 22, bold: true, color: C.text2, valign: "middle", objectName: "tested title" });
  T(s, [
    { text: "Tags over Ethernet into the CSV on the real reader (Linux)", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Reading and decoding the reader's settings", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Start at boot (3 reboots) and restart after a crash", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "HTTP, MQTT and TCP forwarding against test servers", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Spool and automatic resend, password, allow-list, health URL", options: { bullet: true } },
  ], { x: M + 0.35, y: 2.75, w: half - 0.7, h: 3.7, fontSize: 18, objectName: "tested list" });
  await ring(s, W - M - half + 0.3, 1.9, 0.6, HEX.amber, "FaExclamation", HEX.ink, "untested");
  T(s, "Not yet tested", { x: W - M - half + 1.1, y: 1.95, w: 4, h: 0.5, fontSize: 22, bold: true, color: C.text2, valign: "middle", objectName: "untested title" });
  T(s, [
    { text: "Windows and macOS (launchers, auto-start)", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "WiFi and 4G interface on the reader", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Forwarding to a real cloud service", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "One-click button and Restore on the real reader", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Writing RF power and Wiegand values", options: { bullet: true } },
  ], { x: W - M - half + 0.35, y: 2.75, w: half - 0.7, h: 3.7, fontSize: 18, objectName: "untested list" });
  note(s, "Being straight about status. On the left is what we actually exercised. On the right is what is written but not yet proven. The SOP has a test-record table so each person who deploys can record the result for Windows, macOS, WiFi and a real cloud endpoint, and report back.");

  // =============== 14. Closing ===============
  s = pres.addSlide({ masterName: "DARK_CONTENT", sectionTitle: "Status" });
  s.addText("Get it, run it, tell us what breaks", { placeholder: "title" });
  const nxt = [
    ["FaWindows", "Test on Windows and macOS", "Run the launcher, reboot, check auto-start"],
    ["FaWifi", "Try WiFi on the reader", "Interface WIFI plus network name and password"],
    ["FaCloud", "Connect a real endpoint", "HTTP URL or MQTT broker, then unplug to test the spool"],
  ];
  for (let i = 0; i < 3; i++) {
    const y = 1.95 + i * 1.25;
    await ring(s, M, y, 0.85, i === 1 ? HEX.orange : HEX.teal, nxt[i][0], HEX.white, "next icon " + i);
    T(s, nxt[i][1], { x: M + 1.1, y: y - 0.02, w: 6.0, h: 0.45, fontSize: 22, bold: true, color: C.background1, objectName: "next title " + i });
    T(s, nxt[i][2], { x: M + 1.1, y: y + 0.45, w: 6.0, h: 0.4, fontSize: 16, color: C.background2, objectName: "next text " + i });
  }
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.2, y: 1.95, w: 4.53, h: 3.6, rectRadius: 0.12, fill: { color: C.text1 }, line: { color: C.accent5, width: 0.75 }, objectName: "repo card" });
  s.addImage({ data: await icon("FaGithub", HEX.white), x: 8.5, y: 2.25, w: 0.6, h: 0.6, altText: "GitHub icon" });
  T(s, "Private repository", { x: 9.3, y: 2.3, w: 3.3, h: 0.5, fontSize: 20, bold: true, color: C.background1, valign: "middle", objectName: "repo title" });
  T(s, "github.com/C2A-2796/selfmade-reader", { x: 8.45, y: 3.15, w: 4.15, h: 0.4, fontSize: 13, bold: true, color: C.accent2, objectName: "repo url" });
  T(s, "Access by invitation. Start with docs/SOP.md: install, set up, verify, sign off.", { x: 8.5, y: 3.8, w: 4.0, h: 1.2, fontSize: 16, color: C.background2, objectName: "repo text" });
  T(s, "Questions?", { x: M, y: 6.0, w: 5, h: 0.6, fontSize: 28, bold: true, color: C.accent2, fontFace: "Cambria", objectName: "Questions" });
  note(s, "To finish: three things we would like people to try. Test Windows and macOS. Try the reader's WiFi interface. Connect a real HTTP or MQTT endpoint and unplug the network to see the spool work. Everything is in a private GitHub repository by invitation, and the SOP in the docs folder walks through install, setup, verification and sign-off. Thank you; questions?");

  const out = path.join(D, "Selfmade_Reader_Demo.pptx");
  await pres.writeFile({ fileName: out });
  if (applyTheme) await applyTheme(out, THEME);
  console.log("built");
})().catch((e) => { console.error(e); process.exit(1); });
