/*
 * Solaris 2.x on sun4m: halt the CPU in the idle loop
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

/*
 * With one CPU, the idle thread of Solaris 2.5.1 to 9 runs this loop in
 * idle() at interrupt level 0:
 *
 *   while (ncpus == 1) {
 *       if (CPU->cpu_disp.disp_nrunnable != 0)
 *           swtch();
 *       else
 *           (*idle_cpu)();                   <- the translator's hook
 *   }
 *
 * idle_cpu is the CPU module's way to stop the processor. Only the
 * microSPARC-II module sets it, to a function that asks the power
 * management driver (pmc) to write the APC register, which QEMU turns
 * into a halt. On every other CPU, the SuperSPARC of the SPARCstation 10
 * and 20 among them, it is a function that just returns, so the loop
 * spins and keeps a host core busy.
 *
 * The translator finds the call through idle_cpu by the instructions
 * around it (gen_solaris_idle() in translate.c), and takes from them the
 * register and offset by which the loop loads disp_nrunnable. At the call
 * it calls helper_solaris_idle(), which halts the CPU when disp_nrunnable
 * is 0, interrupts are enabled at level 0 and none is pending, which is
 * where idle_cpu exists to stop the processor. On a machine with one CPU
 * only an interrupt handler can then make a thread runnable, and the board
 * turns this on only for one CPU (with more, Solaris runs another loop and
 * a CPU queues work for an idle one without an interrupt). The helper
 * reads disp_nrunnable again, as an interrupt may have come since the loop
 * loaded it.
 *
 * The CPU goes on at the call after the next interrupt (the clock ticks
 * at 100 Hz), so idle_cpu still runs when the loop finds no work, and the
 * guest counts its idle time as before.
 *
 * As in sunos_idle.c, the loop spins on for 100 us before the first halt,
 * as a disk request often completes that soon.
 */

#include "qemu/osdep.h"
#include "qemu/timer.h"
#include "hw/core/cpu.h"
#include "cpu.h"
#include "accel/tcg/cpu-loop.h"
#include "accel/tcg/cpu-mmu-index.h"
#include "accel/tcg/probe.h"
#include "exec/cpu-common.h"
#include "exec/helper-proto.h"
#include "exec/tlb-flags.h"
#include "trace.h"

/*
 * Spin on for this long after the loop first found no work. A round that
 * comes more than SOLARIS_IDLE_GAP_NS after the one before means that the
 * guest left the loop between them.
 */
#define SOLARIS_IDLE_POLL_NS  (100 * SCALE_US)
#define SOLARIS_IDLE_GAP_NS   (20 * SCALE_US)

static bool solaris_idle_polled(CPUSPARCState *env)
{
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);

    if (now - env->solaris_idle_last > SOLARIS_IDLE_GAP_NS) {
        env->solaris_idle_since = now;
    }
    env->solaris_idle_last = now;
    return now - env->solaris_idle_since >= SOLARIS_IDLE_POLL_NS;
}

/* Read a 4-byte kernel variable; false if it is not mapped RAM */
static bool solaris_idle_read(CPUSPARCState *env, target_ulong addr,
                              uint32_t *val)
{
    void *host;
    int flags;

    if (addr & 3) {
        return false;
    }
    flags = probe_access_flags(env, addr, 4, MMU_DATA_LOAD,
                               cpu_mmu_index(env_cpu(env), false), true,
                               &host, 0);
    if ((flags & TLB_INVALID_MASK) || !host) {
        return false;
    }
    *val = ldl_be_p(host);
    return true;
}

/*
 * Solaris is at the call through idle_cpu in its idle loop. Halt until the
 * next interrupt when no thread is runnable, and go on at the call then.
 */
void HELPER(solaris_idle)(CPUSPARCState *env, target_ulong pc,
                          target_ulong nrunnable)
{
    CPUState *cs = env_cpu(env);
    uint32_t val;

    /* Interrupts are enabled and none is pending */
    if (!env->psret || env->psrpil ||
        cpu_test_interrupt(cs, CPU_INTERRUPT_HARD)) {
        return;
    }
    if (!solaris_idle_read(env, nrunnable, &val) || val) {
        return;
    }
    if (!solaris_idle_polled(env)) {
        return;
    }

    trace_sparc_solaris_idle(pc);
    env->pc = pc;
    env->npc = pc + 4;
    cs->halted = 1;
    cs->exception_index = EXCP_HLT;
    cpu_loop_exit(cs);
}
