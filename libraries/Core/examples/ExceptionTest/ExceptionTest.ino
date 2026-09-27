/* Exercises C++ exceptions - select Tools > C++ Exceptions: Enabled (see
 * docs/BUILDING.md "Tools menus"): throw/catch by value and by base class,
 * unwinding through several frames with destructors running, rethrow,
 * library exceptions (std::out_of_range) and std::bad_alloc from a failed
 * `new`. Prints PASS/FAIL per check and a summary every 3 seconds. */
#include <new>
#include <stdexcept>
#include <vector>

static int passed = 0, failed = 0;
static int destructed = 0;

static void check(const char *name, bool ok) {
  Serial.print(ok ? "PASS " : "FAIL ");
  Serial.println(name);
  if (ok) passed++; else failed++;
}

struct Guard {
  ~Guard() { destructed++; }
};

static void throwDeep(int depth) {
  Guard g;
  if (depth == 0) throw std::runtime_error("deep");
  throwDeep(depth - 1);
}

static void rethrower() {
  try {
    throw 7;
  } catch (int) {
    throw;  // rethrow the current exception
  }
}

static void runTests() {
  passed = failed = 0;

  { bool ok = false;
    try { throw 42; } catch (int e) { ok = (e == 42); }
    check("throw int", ok); }

  { bool ok = false;
    try { throw std::runtime_error("boom"); }
    catch (const std::exception &e) { ok = String(e.what()) == "boom"; }
    check("runtime_error caught as std::exception, what()", ok); }

  { bool ok = false; destructed = 0;
    try { throwDeep(5); } catch (const std::runtime_error &) { ok = true; }
    check("unwind 6 frames", ok);
    check("destructors ran during unwinding (6)", destructed == 6); }

  { bool ok = false;
    try { rethrower(); } catch (int e) { ok = (e == 7); }
    check("rethrow", ok); }

  { bool ok = false;
    std::vector<int> v(3);
    try { v.at(10) = 1; } catch (const std::out_of_range &) { ok = true; }
    check("vector::at out_of_range", ok); }

  { bool ok = false; bool gotNull = false;
    try { char *p = new char[64u * 1024u * 1024u]; gotNull = (p == nullptr); delete[] p; }
    catch (const std::bad_alloc &) { ok = true; }
    if (gotNull) Serial.println("  (new returned nullptr instead of throwing)");
    check("new of 64MB throws bad_alloc", ok); }

  { bool ok = false;
    try { throw 3.5f; } catch (...) { ok = true; }
    check("catch (...)", ok); }

  Serial.print("RESULT: ");
  Serial.print(passed);
  Serial.print(" passed, ");
  Serial.print(failed);
  Serial.println(" failed");
}

void setup() {
  Serial.begin(115200);
}

void loop() {
  Serial.println("--- ExceptionTest ---");
  runTests();
  delay(3000);
}
