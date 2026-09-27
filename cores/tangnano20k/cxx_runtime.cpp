/* Minimal C++ runtime support for -nostdlib: libsupc++ isn't linked, so
 * operator new/delete and the static-destructor hook have to come from
 * here. new/delete are backed by the same SDRAM heap as malloc()/free()
 * (tangnano20k_malloc.c). With C++ exceptions disabled (the default)
 * there's nothing to throw, so an exhausted heap makes `new` return
 * nullptr, like the nothrow form on other Arduino cores. */

#include <stddef.h>
#include <stdlib.h>

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

/* Our own abort(): newlib's raises SIGABRT, which drags in _kill(),
 * _getpid() and _exit() - none of which exist on this bare SoC. Called
 * e.g. by libraries built without exceptions when an allocation fails. */
extern "C" void abort(void)
{
  for (;;) {
  }
}

void *operator new(size_t size)
{
  return malloc(size);
}

void *operator new[](size_t size)
{
  return malloc(size);
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
