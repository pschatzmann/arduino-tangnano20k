/* Minimal C++ runtime support for -nostdlib: libsupc++ isn't linked, so
 * operator new/delete and the static-destructor hook have to come from
 * here. new/delete are backed by the same SDRAM heap as malloc()/free()
 * (tangnano20k_malloc.c). With C++ exceptions disabled (the default)
 * there's nothing to throw, so an exhausted heap makes `new` return
 * nullptr, like the nothrow form on other Arduino cores; with them
 * enabled it throws std::bad_alloc. */

#include <stddef.h>
#include <stdlib.h>

#include <new>

extern "C" void *__dso_handle;
void *__dso_handle = nullptr;

/* Static objects are never destroyed on this core (main() never
 * returns), so registering their destructors is a no-op. */
extern "C" int __cxa_atexit(void (*)(void *), void *, void *)
{
  return 0;
}

/* A pure virtual call means a broken object; stop here rather than
 * jumping to a null vtable slot. */
extern "C" void __cxa_pure_virtual(void)
{
  for (;;) {
  }
}

/* Tools > C++ Exceptions: libgcc's unwinder only searches unwind tables
 * that were registered with __register_frame_info(), which crtbegin.o
 * does on a hosted toolchain - this core links with -nostartfiles. The
 * reference is weak, so this is a no-op unless the unwinder is actually
 * linked in (i.e. something throws). __eh_frame_start comes from
 * ldscripts/exceptions/eh_frame.ld, also weak since only that option
 * defines it. */
extern "C" void __register_frame_info(const void *begin, void *object) __attribute__((weak));
extern "C" const char __eh_frame_start[] __attribute__((weak));

__attribute__((constructor)) static void registerEhFrame(void)
{
  static void *object[8]; // libgcc's struct object (6 words), zeroed
  if (__register_frame_info && __eh_frame_start)
    __register_frame_info(__eh_frame_start, object);
}

extern "C" int puts(const char *str);

/* Our own abort(): newlib's raises SIGABRT, which drags in _kill(),
 * _getpid() and _exit() - none of which exist on this bare SoC. Reached
 * e.g. when a library container runs out of memory without exceptions
 * (libstdc++'s bad_alloc then ends in std::terminate()), or on an
 * uncaught exception. Says so on Serial before stopping, rather than
 * hanging silently - puts() writes straight to the UART, no heap needed. */
extern "C" void abort(void)
{
  puts("\nabort(): out of memory or uncaught C++ exception - program stopped");
  for (;;) {
  }
}

/* With Tools > C++ Exceptions enabled (this file is then compiled with
 * -fexceptions), an exhausted heap throws std::bad_alloc as standard C++
 * requires; otherwise `new` returns nullptr, see the top of this file. */
static void *allocate(size_t size)
{
  void *p = malloc(size);
#if defined(__cpp_exceptions)
  if (!p)
    throw std::bad_alloc();
#endif
  return p;
}

void *operator new(size_t size)
{
  return allocate(size);
}

void *operator new[](size_t size)
{
  return allocate(size);
}

void operator delete(void *ptr)
{
  free(ptr);
}

void operator delete[](void *ptr)
{
  free(ptr);
}

void operator delete(void *ptr, size_t)
{
  free(ptr);
}

void operator delete[](void *ptr, size_t)
{
  free(ptr);
}
