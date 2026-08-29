<?php
/**
 * MPYC results landing page.
 *
 * Lists the Sailwave race reports sitting in this directory alongside the
 * season standings tables. Nothing here is hard coded to a season: the
 * current season is worked out from the leaguetable/pointstable files that
 * generate_webcontent.py writes, so this file does not need editing in
 * September each year.
 *
 * Expected filenames in this directory:
 *   "YYMMDD Race name.htm"      - a Sailwave race report
 *   "leaguetableYYYY.htm"       - season league table  (YYYY = e.g. 2526)
 *   "pointstableYYYY.htm"       - season points table
 *   "pointstable_ilcaN_YYYY.htm"- per-class points table, if generated
 *   ...any of the above with a "_fpp" suffix for first-past-the-post
 */

/** A season runs 1 July -> 30 June, so "2526" covers 2025-07-01 to 2026-06-30. */
function mpyc_season_window($code)
{
    $startYear = 2000 + (int) substr($code, 0, 2);

    return array(
        mktime(0, 0, 0, 7, 1, $startYear),
        mktime(23, 59, 59, 6, 30, $startYear + 1),
    );
}

/** "2526" -> "2025/26" */
function mpyc_season_label($code)
{
    return '20' . substr($code, 0, 2) . '/' . substr($code, 2, 2);
}

/**
 * Split the directory listing into race reports and standings tables.
 *
 * Returns array(races, tables) where tables is keyed by season code.
 */
function mpyc_scan($dir)
{
    $races = array();
    $tables = array();

    $entries = @scandir($dir);
    if ($entries === false) {
        return array($races, $tables);
    }

    foreach ($entries as $entry) {
        if ($entry === '.' || $entry === '..' || is_dir($dir . '/' . $entry)) {
            continue;
        }

        // "leaguetable2526.htm", "pointstable_ilca7_2526.htm", "..._fpp.htm"
        if (preg_match('/^(league|points)table(?:_ilca(\d))?_?(\d{4})(_fpp)?\.html?$/i', $entry, $m)) {
            $season = $m[3];
            if (!isset($tables[$season])) {
                $tables[$season] = array();
            }
            $tables[$season][] = array(
                'file' => $entry,
                'type' => strtolower($m[1]),
                'ilca' => $m[2] !== '' ? (int) $m[2] : null,
                'fpp'  => isset($m[4]) && $m[4] !== '',
            );
            continue;
        }

        // "230909 Hutcheson Brothers Cup.htm" or "230128_Volvo_RTE.htm"
        if (preg_match('/^(\d{6})(?:[ _]+(.*?))?\.html?$/i', $entry, $m)) {
            $stamp = mktime(
                12, 0, 0,
                (int) substr($m[1], 2, 2),   // month
                (int) substr($m[1], 4, 2),   // day
                2000 + (int) substr($m[1], 0, 2)
            );
            $title = isset($m[2]) ? trim(str_replace('_', ' ', $m[2])) : '';
            // Names are typed by hand into Sailwave, so tidy the all-lowercase
            // ones without touching deliberate capitals like "RTE".
            if ($title !== '' && $title === strtolower($title)) {
                $title = ucwords($title);
            }

            $races[] = array(
                'file'  => $entry,
                'stamp' => $stamp,
                'title' => $title !== '' ? $title : 'Race report',
            );
        }
    }

    // Newest race first.
    usort($races, 'mpyc_compare_races');
    krsort($tables);

    return array($races, $tables);
}

function mpyc_compare_races($a, $b)
{
    if ($a['stamp'] === $b['stamp']) {
        return strcmp($a['file'], $b['file']);
    }

    return $a['stamp'] < $b['stamp'] ? 1 : -1;
}

/** Human label for a standings table link. */
function mpyc_table_label($table)
{
    if ($table['ilca'] !== null) {
        $label = 'ILCA ' . $table['ilca'] . ' Points';
    } elseif ($table['type'] === 'league') {
        $label = 'League Table';
    } else {
        $label = 'Points Table';
    }

    return $table['fpp'] ? $label . ' (line honours)' : $label;
}

/** Sort standings links into a sensible reading order. */
function mpyc_compare_tables($a, $b)
{
    if ($a['fpp'] !== $b['fpp']) {
        return $a['fpp'] ? 1 : -1;
    }
    if ($a['type'] !== $b['type']) {
        return $a['type'] === 'league' ? -1 : 1;
    }
    if ($a['ilca'] !== $b['ilca']) {
        // Overall table before the per-class breakdowns, then 7, 6, 4.
        if ($a['ilca'] === null) {
            return -1;
        }
        if ($b['ilca'] === null) {
            return 1;
        }

        return $b['ilca'] - $a['ilca'];
    }

    return 0;
}

$dir = __DIR__;
list($allRaces, $tables) = mpyc_scan($dir);

// Current season: the newest one we have a standings table for, otherwise
// infer it from the most recent race report.
$season = null;
if (!empty($tables)) {
    $seasonCodes = array_keys($tables);
    $season = (string) $seasonCodes[0];
} elseif (!empty($allRaces)) {
    $newest = $allRaces[0]['stamp'];
    $year = (int) date('Y', $newest);
    $startYear = (int) date('n', $newest) >= 7 ? $year : $year - 1;
    $season = substr((string) $startYear, 2, 2) . substr((string) ($startYear + 1), 2, 2);
}

$standings = ($season !== null && isset($tables[$season])) ? $tables[$season] : array();
usort($standings, 'mpyc_compare_tables');

// Keep only this season's races on the front page; anything older is a
// leftover from a previous season and belongs in the archive.
$races = $allRaces;
if ($season !== null) {
    list($from, $to) = mpyc_season_window($season);
    $races = array();
    foreach ($allRaces as $race) {
        if ($race['stamp'] >= $from && $race['stamp'] <= $to) {
            $races[] = $race;
        }
    }
    // If nothing lands in the window the directory is laid out differently
    // than expected, so fall back to showing everything rather than nothing.
    if (empty($races)) {
        $races = $allRaces;
    }
}

// Group races under a month heading.
$months = array();
foreach ($races as $race) {
    $key = date('Y-m', $race['stamp']);
    if (!isset($months[$key])) {
        $months[$key] = array('label' => date('F Y', $race['stamp']), 'races' => array());
    }
    $months[$key]['races'][] = $race;
}

$hasLogo = file_exists($dir . '/mpyc_logo.gif');
$hasArchive = is_dir($dir . '/archive');
$seasonLabel = $season !== null ? mpyc_season_label($season) : '';
$raceCount = count($races);

function e($value)
{
    return htmlspecialchars($value, ENT_QUOTES, 'UTF-8');
}

/** Encode a filename for use in a URL but keep it readable. */
function href($file)
{
    return e(str_replace('%2F', '/', rawurlencode($file)));
}
?>
<!doctype html>
<html lang="en-NZ">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MPYC Results<?php echo $seasonLabel !== '' ? ' ' . e($seasonLabel) : ''; ?></title>
<meta name="description" content="Race results and season standings for Mount Pleasant Yacht Club.">
<style>
:root {
  --navy: #0b2545;
  --navy-soft: #13315c;
  --gold: #c8a951;
  --bg: #f4f6f9;
  --card: #ffffff;
  --text: #16202e;
  --muted: #5b6a7d;
  --line: #dde3ec;
  --accent: #1c6dd0;
  --shadow: 0 1px 2px rgba(11, 37, 69, .06), 0 4px 16px rgba(11, 37, 69, .06);
}
@media (prefers-color-scheme: dark) {
  :root {
    --navy: #0a1930;
    --navy-soft: #16305a;
    --bg: #0e1621;
    --card: #16202e;
    --text: #e8edf4;
    --muted: #94a3b8;
    --line: #243349;
    --accent: #6aa9f0;
    --shadow: 0 1px 2px rgba(0, 0, 0, .3), 0 4px 16px rgba(0, 0, 0, .25);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  -webkit-text-size-adjust: 100%;
}
a { color: var(--accent); }
.masthead {
  background: var(--navy);
  border-bottom: 3px solid var(--gold);
  padding: 18px 20px;
}
.masthead-inner {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 14px;
}
.mark {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  overflow: hidden;
  flex: none;
  align-self: center;
  background: var(--navy);
  box-shadow: 0 0 0 1px rgba(200, 169, 81, .5);
}
/* The logo is a roundel on a white square, so clip it and scale past the margin. */
.mark img { display: block; width: 100%; height: 100%; transform: scale(1.12); }
.masthead h1 {
  margin: 0;
  color: #fff;
  font-size: 1.35rem;
  letter-spacing: .01em;
}
.masthead .season {
  color: var(--gold);
  font-weight: 600;
  font-size: 1rem;
}
.wrap { max-width: 900px; margin: 0 auto; padding: 24px 20px 56px; }
section { margin-bottom: 36px; }
h2 {
  font-size: .8rem;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--muted);
  margin: 0 0 12px;
  font-weight: 700;
}
.standings {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 10px;
}
.standings a {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 14px 16px;
  text-decoration: none;
  color: var(--text);
  font-weight: 600;
  box-shadow: var(--shadow);
  transition: transform .12s ease, border-color .12s ease;
}
.standings a:hover { transform: translateY(-1px); border-color: var(--accent); }
.standings .dot {
  width: 9px; height: 9px; border-radius: 50%;
  background: var(--gold); flex: none;
}
.standings a.secondary { font-weight: 500; color: var(--muted); }
.standings a.secondary .dot { background: var(--line); }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}
.toolbar h2 { margin: 0; }
#q {
  flex: 1 1 220px;
  max-width: 320px;
  padding: 9px 12px;
  font-size: .95rem;
  color: var(--text);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8px;
}
#q:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.month { margin-bottom: 22px; }
.month h3 {
  font-size: .95rem;
  margin: 0 0 8px;
  color: var(--muted);
  font-weight: 600;
}
.races {
  list-style: none;
  margin: 0;
  padding: 0;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: var(--shadow);
}
.races li + li { border-top: 1px solid var(--line); }
.races a {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  text-decoration: none;
  color: var(--text);
}
.races a:hover { background: rgba(28, 109, 208, .07); }
.date {
  flex: none;
  width: 54px;
  text-align: center;
  border-right: 1px solid var(--line);
  padding-right: 12px;
  line-height: 1.15;
}
.date .day { display: block; font-size: 1.15rem; font-weight: 700; }
.date .mon {
  display: block;
  font-size: .7rem;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--muted);
}
.name { font-weight: 600; }
.weekday { color: var(--muted); font-weight: 400; font-size: .85rem; }
.empty {
  background: var(--card);
  border: 1px dashed var(--line);
  border-radius: 10px;
  padding: 28px 20px;
  text-align: center;
  color: var(--muted);
}
footer {
  border-top: 1px solid var(--line);
  padding-top: 16px;
  color: var(--muted);
  font-size: .85rem;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  justify-content: space-between;
}
@media (max-width: 480px) {
  .masthead h1 { font-size: 1.1rem; }
  .wrap { padding: 18px 14px 40px; }
}
</style>
</head>
<body>

<header class="masthead">
  <div class="masthead-inner">
<?php if ($hasLogo): ?>
    <span class="mark"><img src="mpyc_logo.gif" alt="" width="150" height="150"></span>
<?php endif; ?>
    <h1>Mount Pleasant Yacht Club</h1>
<?php if ($seasonLabel !== ''): ?>
    <span class="season"><?php echo e($seasonLabel); ?> season</span>
<?php endif; ?>
  </div>
</header>

<div class="wrap">

<?php if (!empty($standings)): ?>
  <section>
    <h2>Season standings</h2>
    <div class="standings">
<?php foreach ($standings as $table): ?>
      <a class="<?php echo $table['fpp'] ? 'secondary' : ''; ?>" href="<?php echo href($table['file']); ?>">
        <span class="dot" aria-hidden="true"></span><?php echo e(mpyc_table_label($table)); ?>
      </a>
<?php endforeach; ?>
    </div>
  </section>
<?php endif; ?>

  <section>
    <div class="toolbar">
      <h2>Race results<?php echo $raceCount ? ' &middot; <span id="count">' . $raceCount . '</span> races' : ''; ?></h2>
<?php if ($raceCount > 6): ?>
      <input id="q" type="search" placeholder="Search races&hellip;" aria-label="Search races" autocomplete="off">
<?php endif; ?>
    </div>

<?php if ($raceCount === 0): ?>
    <p class="empty">No race reports have been uploaded yet this season.</p>
<?php else: ?>
<?php foreach ($months as $month): ?>
    <div class="month">
      <h3><?php echo e($month['label']); ?></h3>
      <ul class="races">
<?php foreach ($month['races'] as $race): ?>
        <li class="race" data-search="<?php echo e(strtolower($race['title'] . ' ' . date('j F Y D', $race['stamp']))); ?>">
          <a href="<?php echo href($race['file']); ?>">
            <span class="date">
              <span class="day"><?php echo date('j', $race['stamp']); ?></span>
              <span class="mon"><?php echo date('M', $race['stamp']); ?></span>
            </span>
            <span>
              <span class="name"><?php echo e($race['title']); ?></span><br>
              <span class="weekday"><?php echo date('l', $race['stamp']); ?></span>
            </span>
          </a>
        </li>
<?php endforeach; ?>
      </ul>
    </div>
<?php endforeach; ?>
    <p class="empty" id="nomatch" hidden>No races match that search.</p>
<?php endif; ?>
  </section>

  <footer>
<?php if ($hasArchive): ?>
    <a href="archive/">Previous seasons &rarr;</a>
<?php else: ?>
    <span></span>
<?php endif; ?>
    <span>Results produced with Sailwave</span>
  </footer>
</div>

<?php if ($raceCount > 6): ?>
<script>
(function () {
  var box = document.getElementById('q');
  if (!box) { return; }

  var races = Array.prototype.slice.call(document.querySelectorAll('.race'));
  var months = Array.prototype.slice.call(document.querySelectorAll('.month'));
  var count = document.getElementById('count');
  var noMatch = document.getElementById('nomatch');

  function filter() {
    var term = box.value.trim().toLowerCase();
    var shown = 0;

    races.forEach(function (race) {
      var hit = term === '' || race.getAttribute('data-search').indexOf(term) !== -1;
      race.hidden = !hit;
      if (hit) { shown++; }
    });

    months.forEach(function (month) {
      month.hidden = !month.querySelector('.race:not([hidden])');
    });

    if (count) { count.textContent = shown; }
    if (noMatch) { noMatch.hidden = shown !== 0; }
  }

  box.addEventListener('input', filter);
  filter();
}());
</script>
<?php endif; ?>

</body>
</html>
