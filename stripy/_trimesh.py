import _tripack
import _srfpack
import numpy as np

__version__ = "1.1"

_ier_codes = {0:  "no errors were encountered.",
              -1: "N < 3 on input.",
              -2: "the first three nodes are collinear.",
              -3: "duplicate nodes were encountered.",
              -4: "an error flag was returned by a call to SWAP in ADDNOD.\n \
                   This is an internal error and should be reported to the programmer.",
              'L':"nodes L and M coincide for some M > L.\n \
                   The linked list represents a triangulation of nodes 1 to M-1 in this case.",
              1: "NCC, N, NROW, or an LCC entry is outside its valid range on input.",
              2: "the triangulation data structure (LIST,LPTR,LEND) is invalid.",
              'K': 'NPTS(K) is not a valid index in the range 1 to N.'}


class Triangulation(object):
    """
    Define a Delaunay triangulation for given Cartesian mesh points (x, y)
    where x and y vectors are 1D numpy arrays of equal length.

    Algorithm
    ---------
     R. J. Renka (1996), Algorithm 751; TRIPACK: a constrained two-
     dimensional Delaunay triangulation package,
     ACM Trans. Math. Softw., 22(1), pp 1–8,
     doi:10.1145/225545.225546.

    Parameters
    ----------
     x : 1D array of Cartesian x coordinates
     y : 1D array of Cartesian y coordinates

    Attributes
    ----------
     x : ndarray of floats, shape (n,)
        stored Cartesian x coordinates from input
     y : ndarray of floats, shape (n,)
        stored Cartesian y coordinates from input
     simplices : ndarray of ints, shape (nsimplex, 3)
        indices of the points forming the simplices in the triangulation
        points are ordered anticlockwise
     lst : ndarray of ints, shape (6n-12,)
        nodal indices with lptr and lend, define the triangulation as a set of N
        adjacency lists; counterclockwise-ordered sequences of neighboring nodes
        such that the first and last neighbors of a boundary node are boundary
        nodes (the first neighbor of an interior node is arbitrary).  In order to
        distinguish between interior and boundary nodes, the last neighbor of
        each boundary node is represented by the negative of its index.
        The indices are 1-based (as in Fortran), not zero based (as in python).
     lptr : ndarray of ints, shape (6n-12),)
        set of pointers in one-to-one correspondence with the elements of lst.
        lst(lptr(i)) indexes the node which follows lst(i) in cyclical
        counterclockwise order (the first neighbor follows the last neighbor).
        The indices are 1-based (as in Fortran), not zero based (as in python).
     lend : ndarray of ints, shape (n,)
        N pointers to adjacency lists.
        lend(k) points to the last neighbor of node K. 
        lst(lend(K)) < 0 if and only if K is a boundary node.
        The indices are 1-based (as in Fortran), not zero based (as in python).
    """
    def __init__(self, x, y):

        if len(x.shape) != 1 or len(y.shape) != 1:
            raise ValueError('x and y must be 1D')

        if x.size != y.size:
            raise ValueError('x and y must have same length')

        # Triangulation
        lst, lptr, lend, ierr = _tripack.trmesh(x,y)

        if ierr != 0:
            raise ValueError('ierr={} in trmesh\n{}'.format(ierr, _ier_codes[ierr]))

        self.x = x
        self.y = y
        self.npoints = x.size

        self.lst = lst
        self.lptr = lptr
        self.lend = lend

        # Convert a triangulation to a triangle list form (human readable)
        # Uses an optimised version of trlist that returns triangles
        # without neighbours or arc indices
        nt, ltri, ierr = _tripack.trlist2(lst, lptr, lend)

        if ierr != 0:
            raise ValueError('ierr={} in trlist2\n{}'.format(ierr, _ier_codes[ierr]))

        # extract triangle list and convert to zero-based ordering
        self.simplices = ltri.T[:nt] - 1


    def neighbour_simplices(self):
        """
        Get indices of neighbour simplices for each simplex.
        The kth neighbour is opposite to the kth vertex.
        For simplices at the boundary, -1 denotes no neighbour.
        """
        nt, ltri, lct, ierr = _tripack.trlist(self.lst, self.lptr, self.lend, nrow=6)
        if ierr != 0:
            raise ValueError('ierr={} in trlist\n{}'.format(ierr, _ier_codes[ierr]))
        return ltri.T[:nt,3:] - 1


    def neighbour_and_arc_simplices(self):
        """
        Get indices of neighbour simplices for each simplex and arc indices.
        Identical to get_neighbour_simplices() but also returns an array
        of indices that reside on boundary hull, -1 denotes no neighbour.
        """
        nt, ltri, lct, ierr = _tripack.trlist(self.lst, self.lptr, self.lend, nrow=9)
        if ierr != 0:
            raise ValueError('ierr={} in trlist\n{}'.format(ierr, _ier_codes[ierr]))
        ltri = ltri.T[:nt] - 1
        return ltri[:,3:6], ltri[:,6:]


    def nearest_neighbour(self, xi, yi):
        """
        Get the index of the nearest neighbour to a point (xi,yi)
        and return the squared distance between (xi,yi) and
        its nearest neighbour.

        Notes
        -----
         Faster searches can be obtained using a KDTree.
         Store all x and y coordinates in a KDTree, then query
         a set of points to find their nearest neighbours.
        """
        # i is the node at which we start the search
        i = ((self.x - xi)**2).argmin() + 1
        idx, d = _tripack.nearnd(xi, yi, i, self.x, self.y, self.lst, self.lptr, self.lend)
        return idx - 1, d

    def nearest_neighbours(self, indices, distances, copy=False):
        """
        Determines the ordered sequence of L closest nodes to a given node,
        along with the associated distances. The distance between nodes is
        taken to be the length of the shortest connecting path.

        Parameters
        ----------
         indices : ndarray of ints, shape (n,)
            the indices of the n-1 closest nodes to indices[0] in the first
            n-1 locations. On output, updated with the index of the n-th
            closest node to index[0]
         distances : ndarray of floats, shape (n,)
            the distance between indices(1) and indices(i) in the n-th
            position for i = 0,...,n-1. Thus, distances[0] = 0. 
            On output, updated with the distance between indices[0]
            and indices(i) in position n-1.
         copy : bool (default: False)
            controls whether indices and distances are updated in-place
            or copied to another array (set to True)

        Notes
        -----
         indices contain the indexes of n-1 nodes which must be ordered
         by distance from indices[0].

         The input parameters, indices and distances, are updated in-place.
         A pointer to the data is returned.
        """
        if copy:
            ind = indices.copy()
            dist = distances.copy()
        else:
            ind = indices
            dist = distances
        ind += 1 # convert to 1-based ordering
        _tripack.getnp(x, y, lst, lptr, lend, ind, dist)
        ind -= 1 # convert back to 0-based ordering
        return indices, distances


    def gradient(self, f, nit=3, tol=1e-3, guarantee_convergence=False):
        """
        Return the gradient of an n-dimensional array.

        The method consists of minimizing a quadratic functional Q(G) over
        gradient vectors (in x and y directions), where Q is an approximation
        to the linearized curvature over the triangulation of a C-1 bivariate
        function F(x,y) which interpolates the nodal values and gradients.

        Parameters
        ----------
         f : array of floats, shape (n,)
            field over which to evaluate the gradient
         nit: int (default: 3)
            number of iterations to reach a convergence tolerance, tol
            nit >= 1
         tol: float (default: 1e-3)
            maximum change in gradient between iterations.
            convergence is reached when this condition is met.

        Returns
        -------
         dfdx : array of floats, shape (n,)
            derivative of f in the x direction
         dfdy : array of floats, shape (n,)
            derivative of f in the y direction

        Notes
        -----
         For SIGMA = 0, optimal efficiency was achieved in testing with
         tol = 0, and nit = 3 or 4.

         The restriction of F to an arc of the triangulation is taken to be
         the Hermite interpolatory tension spline defined by the data values
         and tangential gradient components at the endpoints of the arc, and
         Q is the sum over the triangulation arcs, excluding interior
         constraint arcs, of the linearized curvatures of F along the arcs --
         the integrals over the arcs of D2F(T)**2, where D2F(T) is the second
         derivative of F with respect to distance T along the arc.
        """
        if f.size != self.npoints:
            raise ValueError('f should be the same size as mesh')

        gradient = np.zeros((2,self.npoints), order='F', dtype=np.float32)
        sigma = 0
        use_sigma_array = 0

        ierr = 1
        while ierr == 1:
            ierr = _srfpack.gradg(self.x, self.y, f, self.lst, self.lptr, self.lend,\
                                  use_sigma_array, sigma, gradient, nit=nit, dgmax=tol)
            if not guarantee_convergence:
                break

        if ierr < 0:
            raise ValueError('ierr={} in gradg\n{}'.format(ierr, _ier_codes[ierr]))

        return gradient[0], gradient[1]


    def gradient_local(self, f, index):
        """
        Return the gradient at a specified node.

        This routine employs a local method, in which values depend only on nearby
        data points, to compute an estimated gradient at a node.

        gradient_local() is more efficient than gradient() only if it is unnecessary
        to compute gradients at all of the nodes. Both routines have similar accuracy.

        Parameters
        ----------
        """
        if f.size != self.npoints:
            raise ValueError('f should be the same size as mesh')


        gradX, gradY, l = _srfpack.gradl(index + 1, self.x, self.y, f,\
                                         self.lst, self.lptr, self.lend)

        return gradX, gradY



    def interpolate_linear(self, xi, yi, zdata):
        """
        Piecewise linear interpolation/extrapolation to arbitrary point(s).
        The method is fast, but has only C^0 continuity.

        Parameters
        ----------
         xi : float / ndarray of floats, shape (l,)
            x coordinates on the Cartesian plane
         yi : float / ndarray of floats, shape (l,)
            y coordinates on the Cartesian plane
         zdata : ndarray of floats, shape (n,)
            value at each point in the triangulation
            must be the same size of the mesh

        Returns
        -------
         zi : float / ndarray of floats, shape (l,)
            interpolated value(s) of (xi,yi)
        """

        if zdata.size != self.npoints:
            raise ValueError('zdata should be same size as mesh')

        if np.array(xi).size > 1:
            if xi.size != yi.size:
                raise ValueError('xi and yi must have same length')

            n = xi.size
            zi = np.empty(n)
            ist = 1
            
            # iterate
            for i in range(0,n):
                zi[i], t = _srfpack.intrc0(xi[i], yi[i], self.x, self.y, zdata,\
                                           self.lst, self.lptr, self.lend, ist)
        else:
            ist = 1
            zi, t = _srfpack.intrc0(xi, yi, self.x, self.y, zdata,\
                                    self.lst, self.lptr, self.lend, ist)

        return zi


    def interpolate_cubic(self, xi, yi, zdata, derivatives=False):
        """
        Cubic spline interpolation/extrapolation to arbirary point(s).
        This method has C^1 continuity.

        Parameters
        ----------
         xi : float / ndarray of floats, shape (l,)
            x coordinates on the Cartesian plane
         yi : float / ndarray of floats, shape (l,)
            y coordinates on the Cartesian plane
         zdata : ndarray of floats, shape (n,)
            value at each point in the triangulation
            must be the same size of the mesh
         derivatives : bool (default: False)
            optionally returns the first derivatives at point(s) (xi,yi)

        Returns
        -------
         zi : float / ndarray of floats, shape (l,)
            interpolated value(s) of (xi,yi)
         dzx, dzy (optional) : float, ndarray of floats, shape(l,)
            first partial derivatives in x and y direction at (xi,yi)
        """

        if zdata.size != self.npoints:
            raise ValueError('zdata should be same size as mesh')

        if np.array(xi).size > 1:
            if xi.size != yi.size:
                raise ValueError('xi and yi must have same length')

            n = xi.size
            zi  = np.empty(n)
            dzx = np.empty(n)
            dzy = np.empty(n)
            ist = 1
            
            # iterate
            for i in range(0,n):
                zi[i], dzx[i], dzy[i], t = _srfpack.intrc1(xi[i], yi[i], self.x, self.y, zdata,\
                                                           self.lst, self.lptr, self.lend, ist)
        else:
            ist = 1
            zi, dzx, dzy, t = _srfpack.intrc1(xi, yi, self.x, self.y, zdata,\
                                              self.lst, self.lptr, self.lend, ist)

        if derivatives:
            return zi, (dzx, dzy)
        else:
            return zi


    def smoothing(self, f, w, sm, smtol, gstol):
        """
        Smooths a surface f by choosing nodal function values and gradients to
        minimize the linearized curvature of F subject to a bound on the
        deviation from the data values. This is more appropriate than interpolation
        when significant errors are present in the data.

        Parameters
        ----------
         f : ndarray of floats, shape (n,)
            field to apply smoothing on
         w : ndarray of floats, shape (n,)
            weights associated with data value in f
            w[i] = 1/sigma_f^2 is a good rule of thumb.
         sm : float
            positive parameter specifying an upper bound on Q2(f).
            generally n-sqrt(2n) <= sm <= n+sqrt(2n)
         smtol : float
            specifies relative error in satisfying the constraint
            sm(1-smtol) <= Q2 <= sm(1+smtol) between 0 and 1.
         gstol : float
            tolerance for convergence.
            gstol = 0.05*mean(sigma_f)^2 is a good rule of thumb.

        """
        if f.size != self.npoints or f.size != w.size:
            raise ValueError('f and w should be the same size as mesh')

        sigma = 0
        use_sigma_array = 0

        f_smooth, d2f, ierr = _srfpack.smsurf(self.x, self.y, f, self.lst, self.lptr, self.lend,\
                                              use_sigma_array, sigma, w, sm, smtol, gstol)

        if ierr < 0:
            raise ValueError('ierr={} in gradg\n{}'.format(ierr, _ier_codes[ierr]))
        if ierr == 1:
            raise RuntimeWarning("No errors were encountered but the constraint is not active --\n\
                  F, FX, and FY are the values and partials of a linear function \
                  which minimizes Q2(F), and Q1 = 0.")

        return f_smooth, (d2f[0], d2f[1])
