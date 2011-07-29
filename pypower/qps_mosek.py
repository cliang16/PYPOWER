# Copyright (C) 2010-2011 Power System Engineering Research Center
# Copyright (C) 2010-2011 Richard Lincoln
#
# PYPOWER is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# PYPOWER is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY], without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PYPOWER. If not, see <http://www.gnu.org/licenses/>.

"""Quadratic Program Solver based on MOSEK.
"""

from sys import stdout, stderr

from numpy import array, Inf, zeros, shape, tril
from numpy import flatnonzero as find

from scipy.sparse import csr_matrix as sparse

try:
    from pymosek import mosekopt
except ImportError:
#    print 'MOSEK not available'
    pass

from pypower.mosek_options import mosek_options


def qps_mosek(H, c=None, A=None, l=None, u=None, xmin=None, xmax=None,
              x0=None, opt=None):
    """Quadratic Program Solver based on MOSEK.

    A wrapper function providing a PYPOWER standardized interface for using
    MOSEKOPT to solve the following QP (quadratic programming) problem::

        min 1/2 x'*H*x + c'*x
         x

    subject to::

        l <= A*x <= u       (linear constraints)
        xmin <= x <= xmax   (variable bounds)

    Inputs (all optional except C{H}, C{C}, C{A} and C{L}):
        - C{H} : matrix (possibly sparse) of quadratic cost coefficients
        - C{C} : vector of linear cost coefficients
        - C{A, l, u} : define the optional linear constraints. Default
        values for the elements of L and U are -Inf and Inf, respectively.
        - xmin, xmax : optional lower and upper bounds on the
        C{x} variables, defaults are -Inf and Inf, respectively.
        - C{x0} : optional starting value of optimization vector C{x}
        - C{opt} : optional options structure with the following fields,
        all of which are also optional (default values shown in parentheses)
            - C{verbose} (0) - controls level of progress output displayed
                - 0 = no progress output
                - 1 = some progress output
                - 2 = verbose progress output
            - C{max_it} (0) - maximum number of iterations allowed
                - 0 = use algorithm default
            - C{mosek_opt} - options struct for MOSEK, values in
            C{verbose} and C{max_it} override these options
        - C{problem} : The inputs can alternatively be supplied in a single
        C{problem} struct with fields corresponding to the input arguments
        described above: C{H, c, A, l, u, xmin, xmax, x0, opt}

    Outputs:
        - C{x} : solution vector
        - C{f} : final objective function value
        - C{exitflag} : exit flag
              - 1 = success
              - 0 = terminated at maximum number of iterations
              - -1 = primal or dual infeasible
              < 0 = the negative of the MOSEK return code
        - C{output} : output dict with the following fields:
            - C{r} - MOSEK return code
            - C{res} - MOSEK result dict
        - C{lmbda} : dict containing the Langrange and Kuhn-Tucker
        multipliers on the constraints, with fields:
            - C{mu_l} - lower (left-hand) limit on linear constraints
            - C{mu_u} - upper (right-hand) limit on linear constraints
            - C{lower} - lower bound on optimization variables
            - C{upper} - upper bound on optimization variables

    @author: Ray Zimmerman (PSERC Cornell)
    @author: Richard Lincoln
    """
    ##----- input argument handling  -----
    ## gather inputs
    if isinstance(H, dict):       ## problem struct
        p = H
    else:                                ## individual args
        p = {'H': H, 'c': c, 'A': A, 'l': l, 'u': u}
        if xmin is not None:
            p['xmin'] = xmin
        if xmax is not None:
            p['xmax'] = xmax
        if x0 is not None:
            p['x0'] = x0
        if opt is not None:
            p['opt'] = opt

    ## define nx, set default values for H and c
    if 'H' not in p or len(p['H']) or not any(any(p['H'])):
        if ('A' not in p) | len(p['A']) == 0 & \
                ('xmin' not in p) | len(p['xmin']) == 0 & \
                ('xmax' not in p) | len(p['xmax']) == 0:
            stderr.write('qps_mosek: LP problem must include constraints or variable bounds\n')
        else:
            if 'A' in p & len(p['A']) > 0:
                nx = shape(p['A'])[1]
            elif 'xmin' in p & len(p['xmin']) > 0:
                nx = len(p['xmin'])
            else:    # if isfield(p, 'xmax') && ~isempty(p.xmax)
                nx = len(p['xmax'])
        p['H'] = sparse((nx, nx))
        qp = 0
    else:
        nx = shape(p['H'])[0]
        qp = 1

    if 'c' not in p | len(p['c']) == 0:
        p['c'] = zeros(nx)

    if 'x0' not in p | len(p['x0']) == 0:
        p['x0'] = zeros(nx)

    ## default options
    if 'opt' not in p:
        p['opt'] = []

    if 'verbose' in p['opt']:
        verbose = p['opt']['verbose']
    else:
        verbose = 0

    if 'max_it' in p['opt']:
        max_it = p['opt']['max_it']
    else:
        max_it = 0

    if 'mosek_opt' in p['opt']:
        mosek_opt = mosek_options(p['opt']['mosek_opt'])
    else:
        mosek_opt = mosek_options()

    if max_it:
        mosek_opt['MSK_IPAR_INTPNT_MAX_ITERATIONS'] = max_it

    if qp:
        mosek_opt['MSK_IPAR_OPTIMIZER'] = 0   ## default solver only for QP

    ## set up problem struct for MOSEK
    prob = {}
    prob['c'] = p['c']
    if qp:
        prob['qosubi'], prob['qosubj'], prob['qoval'] = find(tril(sparse(p['H'])))

    if 'A' in p & len(p['A']) > 0:
        prob['a'] = sparse(p['A'])

    if 'l' in p & len(p['A']) > 0:
        prob['blc'] = p['l']

    if 'u' in p & len(p['A']) > 0:
        prob['buc'] = p['u']

    if 'xmin' in p & len(p['xmin']) > 0:
        prob['blx'] = p['xmin']

    if 'xmax' in p & len(p['xmax']) > 0:
        prob['bux'] = p['xmax']

    ## A is not allowed to be empty
    if 'a' not in prob | len(prob['a']) == 0:
        unconstrained = True
        prob['a'] = sparse((1, (1, 1)), (1, nx))
        prob.blc = -Inf
        prob.buc =  Inf
    else:
        unconstrained = False

    ##-----  run optimization  -----
    cmd = 'minimize echo(%d)' % verbose
    r, res = mosekopt(cmd, prob, mosek_opt)

    ##-----  repackage results  -----
    if 'sol' in res:
        if 'bas' in res['sol']:
            sol = res['sol.bas']
        else:
            sol = res['sol.itr']
        x = sol['xx']
    else:
        sol = array([])
        x = array([])

    ##-----  process return codes  -----
    if 'symbcon' in res:
        sc = res['symbcon']
    else:
        r2, res2 = mosekopt('symbcon echo(0)')
        sc = res2['symbcon']

    eflag = -r
    msg = ''
    if r == sc.MSK_RES_OK:
        if len(sol) > 0:
#            if sol['solsta'] == sc.MSK_SOL_STA_OPTIMAL:
            if sol['solsta'] == 'OPTIMAL':
                msg = 'The solution is optimal.'
                eflag = 1
            else:
                eflag = -1
#                if sol['prosta'] == sc['MSK_PRO_STA_PRIM_INFEAS']:
                if sol['prosta'] == 'PRIMAL_INFEASIBLE':
                    msg = 'The problem is primal infeasible.'
#                elif sol['prosta'] == sc['MSK_PRO_STA_DUAL_INFEAS']:
                elif sol['prosta'] == 'DUAL_INFEASIBLE':
                    msg = 'The problem is dual infeasible.'
                else:
                    msg = sol['solsta']

    elif r == sc['MSK_RES_TRM_MAX_ITERATIONS']:
        eflag = 0
        msg = 'The optimizer terminated at the maximum number of iterations.'
    else:
        if 'rmsg' in res and 'rcodestr' in res:
            msg = '%s : %s' % (res['rcodestr'], res['rmsg'])
        else:
            msg = 'MOSEK return code = %d' % r

    if verbose and len(msg) > 0:
        stdout.write('%s\n' % msg)

    ##-----  repackage results  -----
    if r == 0:
        f = p['c'].T * x
        if len(p['H']) > 0:
            f = 0.5 * x.T * p['H'] * x + f
    else:
        f = array([])

    output = {}
    output['r'] = r
    output['res'] = res

    if 'sol' in res:
        lmbda = {}
        lmbda['lower'] = sol['slx']
        lmbda['upper'] = sol['sux']
        lmbda['mu_l']  = sol['slc']
        lmbda['mu_u']  = sol['suc']
        if unconstrained:
            lmbda['mu_l']  = array([])
            lmbda['mu_u']  = array([])
    else:
        lmbda = array([])

    return x, f, eflag, output, lmbda