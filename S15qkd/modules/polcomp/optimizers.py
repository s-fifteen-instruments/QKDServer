#!/usr/bin/env python
"""Holds optimization routines for polarization compensation."""

import multiprocessing

import numpy as np
import scipy.optimize


def run_manual_optimizer(optimizer, args=(), kwargs={}):
    """Starts optimizer in a separate process and retuns a manual callback.

    Note that optimizer termination is signaled by raising of 'StopIteration' exception,
    so this needs to be wrapped in a try-except. Since the optimizer uses manual
    callbacks, the args and kwargs should not be populated with the first parameter 'f'
    of the optimizer.

    Note:
        Rather than letting the optimizer push a configuration change and poll
        for measurement results, we instead reverse it: measurement results are
        pushed to the optimizer, which in turn recommends a new configuration.
        This effectively decouples the optimizer from the polarization
        compensation execution thread, much like the existing architecture in QKDServer.
    """
    # Create duplex pipe for sending/receiving results from the optimizer
    parent_conn, child_conn = multiprocessing.Pipe()

    # Wrap child connection for use in optimizer
    def f(x):
        child_conn.send(x)
        y = child_conn.recv()
        if y is None:
            child_conn.close()
            raise StopIteration
        return y

    args = (f,) + tuple(args)
    if "f" in kwargs:
        raise ValueError("Keyword 'f' is disabled.")
    p = multiprocessing.Process(target=optimizer, args=args, kwargs=kwargs, daemon=True)
    p.start()

    # Wrap parent connection in a simple function
    parent_conn.recv()  # discard initial bootstrapped value, i.e. equal to x0

    def result_callback(y):
        parent_conn.send(y)
        if y is None:
            parent_conn.close()
            return
        return parent_conn.recv()

    return result_callback


def minimize_neldermead(f, x0, step, bounds, simplex=None):
    """Runs Nelder-Mead minimizer with callback."""
    if simplex is None:
        simplex = generate_simplex(x0, step, bounds)
        x0 = simplex[0]  # applied clipping
    options = {"initial_simplex": simplex}
    try:
        scipy.optimize.minimize(
            f,
            x0,
            bounds=bounds,
            method="Nelder-Mead",
            options=options,
        )
    except StopIteration:
        pass


def generate_simplex(vertex, step=1, bounds=None):
    """Returns a simplex with origin vertex, and unit step in each dimension.

    This provides an initial search area for the Nelder-Mead algorithm.
    If 'step' is an array, it should match the dimension of the provided
    origin vertex, otherwise it should be single-valued for broadcasting to
    the shape of the vertex. If 'bounds' is provided, it should be an array
    of 2-tuples representing the minimum and maximum for each dimension.

    The 'step' applied is considered independent of polarity, i.e. a step in
    the negative direction is also valid. Extra bound checking is performed
    to choose steps for each dimension so that the number of boundary clips
    needed is minimized.

    Usage:
        >>> generate_simplex([0,1], 2).astype(int).tolist()
        [[0, 1], [2, 1], [0, 3]]

        >>> generate_simplex([1,1,1], [1,2,3]).astype(int).tolist()
        [[1, 1, 1], [2, 1, 1], [1, 3, 1], [1, 1, 4]]

        # The simplex before clippping is [(0,1), (2,1), (0,3)]
        >>> generate_simplex([0,1], 2, bounds=[(0,1),(0,1)]).astype(int).tolist()
        [[0, 1], [1, 1], [0, 1]]

        # The last point transforms to (0,2) and (0,0) for positive and negative
        # step respectively. Since (0,2) -> (0,1) requires one clip while (0,0) does
        # not, the negative step is preferentially chosen. If the number of clips
        # needed is the same, the positive step is the default.
        >>> generate_simplex([0,1], 1, bounds=[(0,1),(0,1)]).astype(int).tolist()
        [[0, 1], [1, 1], [0, 0]]
    """
    vertex = np.array(vertex)
    assert vertex.ndim == 1
    d = vertex.size

    # Generate simplex with origin and unit step in each dimension
    unit_simplex = np.vstack(
        [
            np.zeros(d),
            np.identity(d),
        ]
    )
    step = np.array(step)
    assert step.ndim == 0 or step.shape == (d,)
    simplex = unit_simplex * step + vertex  # scale + translate
    simplex2 = unit_simplex * -step + vertex  # inverted steps

    # Apply boundary conditions
    if bounds is not None:
        bounds = np.array(bounds)
        assert bounds.shape == (d, 2)

        # Perform clipping
        _simplex = np.clip(simplex, *bounds.T)
        _simplex2 = np.clip(simplex2, *bounds.T)

        # Try to minimize amount of correction
        corr = np.sum(np.abs(_simplex - simplex), axis=1)
        corr2 = np.sum(np.abs(_simplex2 - simplex2), axis=1)
        cond = corr <= corr2
        cond = np.broadcast_to(
            cond, (d, d + 1)
        ).T  # workaround for selecting/rejecting entire points
        simplex = np.where(cond, _simplex, _simplex2)

    return simplex


def generate_tetrahedron(vertex, step=1, bounds=None, randomize=False):
    """Returns a regular tetrahedron centered at the vertex and unit edges.

    This generates a 3-simplex centered at the vertex, so that the 3D
    parameter search space can be symmetrically probed during the Nelder-
    Mead algorithm. Note this assumes all the dimensions are of the same scale.

    The nominal coordinates are (1,1,1), (1,-1,-1), (-1,1,-1), (-1,-1,1),
    of edge lengths 2sqrt(2). This configuration is chosen because it has a
    simple dual, which can be easily randomized.
    """
    vertex = np.array(vertex)
    assert vertex.ndim == 1
    d = vertex.size

    # Apply randomization
    step = np.array(step)
    assert step.ndim == 0
    if randomize:
        sign = np.random.randint(2) * 2 - 1  # -1 or 1
        step = step * sign

    # Generate tetrahedron
    unit_tetra = np.array(
        [
            [1, 1, 1],
            [1, -1, -1],
            [-1, 1, -1],
            [-1, -1, 1],
        ]
    ) / (2 * np.sqrt(2))
    simplex = unit_tetra * step + vertex

    # Apply boundary conditions
    if bounds is not None:
        bounds = np.array(bounds)
        assert bounds.shape == (d, 2)
        simplex = np.clip(simplex, *bounds.T)

    return simplex
