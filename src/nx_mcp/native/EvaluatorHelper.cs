using System;
using System.Collections.Generic;
using NXOpen;
using NXOpen.UF;

namespace NxMcp.Native
{
    // Private fixed helper, invoked only on NX's serialized session thread.
    // No evaluator pointers cross the language boundary.
    public static class EvaluatorHelper
    {
        private static int allocated;
        private static int released;
        public static double[] Ping() { return new double[] { 1.0 }; }
        public static double[] Audit() { return new double[] { 1.0, allocated, released, allocated - released }; }
        private static int NativeCode(Exception error)
        {
            NXException native = error as NXException;
            return native == null ? 0 : native.ErrorCode;
        }
        public static double[] InspectChecked(TaggedObject source, int count, bool failAfterAllocation)
        {
            try { return Inspect(source, count, failAfterAllocation); }
            catch (AggregateException both)
            {
                return new double[] { -1, NativeCode(both.InnerExceptions[0]), NativeCode(both.InnerExceptions[1]), 1 };
            }
            catch (InvalidOperationException error)
            {
                if (error.Message == "Evaluator release failed")
                    return new double[] { -1, 0, NativeCode(error.InnerException), 1 };
                return new double[] { -1, NativeCode(error), 0, 0 };
            }
            catch (Exception error) { return new double[] { -1, NativeCode(error), 0, 0 }; }
        }
        public static double[] Inspect(TaggedObject source, int count, bool failAfterAllocation)
        {
            if (source == null || count < 2 || count > 200)
                throw new ArgumentException("Expected a curve/edge and 2..200 samples");
            UFEval api = UFSession.GetUFSession().Eval;
            IntPtr evaluator = IntPtr.Zero;
            Exception primary = null;
            try
            {
                api.Initialize2(source.Tag, out evaluator);
                if (evaluator == IntPtr.Zero) throw new InvalidOperationException("Evaluator allocation returned null");
                allocated++;
                if (failAfterAllocation) throw new InvalidOperationException("NX_MCP_TEST_FAILURE_AFTER_ALLOCATION");
                double[] limits = new double[2];
                api.AskLimits(evaluator, limits);
                List<double> result = new List<double>();
                bool isLine, isArc;
                api.IsLine(evaluator, out isLine); api.IsArc(evaluator, out isArc);
                result.Add(1.0); result.Add(isLine ? 1.0 : (isArc ? 2.0 : 0.0));
                result.Add(count); result.Add(limits[0]); result.Add(limits[1]);
                double radius = 0;
                double[] center = new double[3], xAxis = new double[3], yAxis = new double[3];
                if (isArc)
                {
                    UFEval.Arc arc;
                    api.AskArc(evaluator, out arc);
                    radius = arc.radius; center = arc.center; xAxis = arc.x_axis; yAxis = arc.y_axis;
                }
                result.Add(radius); result.AddRange(center); result.AddRange(xAxis); result.AddRange(yAxis);
                for (int i = 0; i < count; i++)
                {
                    double[] point = new double[3];
                    api.EvaluateUnitVectors(evaluator, limits[0] + (limits[1] - limits[0]) * i / (count - 1), point, new double[3], new double[3], new double[3]);
                    foreach (double value in point)
                    {
                        if (Double.IsNaN(value) || Double.IsInfinity(value)) throw new InvalidOperationException("Nonfinite evaluated point");
                        result.Add(value);
                    }
                }
                return result.ToArray();
            }
            catch (Exception error) { primary = error; throw; }
            finally
            {
                if (evaluator != IntPtr.Zero)
                {
                    try { api.Free(evaluator); released++; }
                    catch (Exception cleanup)
                    {
                        if (primary != null) throw new AggregateException("Evaluator operation and release failed", primary, cleanup);
                        throw new InvalidOperationException("Evaluator release failed", cleanup);
                    }
                }
            }
        }
    }
}
