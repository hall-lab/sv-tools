#!/usr/bin/env python

import argparse
import sys
import numpy as np
import pandas as pd
from scipy.stats import multivariate_normal
from collections import namedtuple
import statsmodels.formula.api as smf
import warnings
from svtools.vcf.file import Vcf
from svtools.vcf.variant import Variant
import svtools.utils as su

vcf_rec = namedtuple('vcf_rec', 'var_id sample svtype AF GT CN AB batch')


def recluster(df):
    df = df[(df.AB != ".")].copy()
    df.loc[:, 'AB'] = pd.to_numeric(df.loc[:, 'AB'])
    df.loc[:, 'CN'] = pd.to_numeric(df.loc[:, 'CN'])
    tp = df.iloc[0, :].loc['svtype']

    gt_code = {'0/0': 1, '0/1': 2, '1/1': 3}
    gt_code_rev = {1: '0/0', 2: '0/1', 3: '1/1'}
    df.loc[:, 'gtn'] = df.loc[:, 'GT'].map(gt_code)

    if tp == 'DEL' or tp == 'MEI':
        batches = []
        for batch in np.unique(df.index):
            batch_df = df.loc[[batch]]
            recluster_DEL(batch_df)
            re_recluster_DEL(batch_df)
            batch_df.loc[:, 'GTR'] = batch_df.loc[:, 'gt_new_re'].map(gt_code_rev)
            batches.append(batch_df)
        df = pd.concat(batches)
    #elif tp in ['DUP']:
    #    # NOTE This is currently not utilized
    #    recluster_DUP(df)
    #    re_recluster_DUP(df)
    #    df.loc[:, 'GTR'] = df.loc[:, 'GT'].copy()
    return df


def recluster_DEL(df):
    # priors
    mu_0 = {
        1: np.array([0.03, 2]),
        2: np.array([0.46, 1.1]),
        3: np.array([0.94, 0.1])
        }
    psi = {
        1: np.matrix('0.00128 -0.00075; -0.00075 1.1367'),
        2: np.matrix('0.013 -0.0196; -0.0196 0.4626'),
        3: np.matrix('0.0046 -0.0112; -0.0112 0.07556')
        }
    lambda_0 = 1

    gpd = df.loc[:, ['gtn', 'CN', 'AB']].groupby(['gtn'])
    covs = gpd[['AB', 'CN']].cov()
    mns = gpd[['AB', 'CN']].mean()
    cts = gpd.size()

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        lin_fit = smf.ols('CN ~ AB', df).fit()
        df.loc[:, 'gt_adj'] = df.loc[:, 'gtn'].copy()
        # Check that CN, AB are correlated, and in the right direction
        if (lin_fit.rsquared > 0.5) and (-1 * lin_fit.params[1] > 0.5):
            x_int = -lin_fit.params[0] / lin_fit.params[1]
            # Adjust init GT calls if AB shifted toward 0
            if x_int < 1:
                # Find mdpts between neighboring GT
                mins = gpd['AB'].min()
                maxes = gpd['AB'].max()
                bound1 = 0.2
                bound2 = 0.7
                if (2 in mins) and (1 in maxes):
                    bound1 = 0.5 * (mins[2] + maxes[1])
                if (3 in mins) and (2 in maxes):
                    bound2 = 0.5 * (mins[3] + maxes[2])
                newbound1 = bound1 * x_int
                newbound2 = bound2 * x_int
                df.loc[:, 'gt_adj'] = pd.to_numeric(
                    pd.cut(
                        df['AB'],
                        bins=[-1, newbound1, newbound2, 1],
                        labels=['1', '2', '3']
                        )
                    )
                gpd = df.loc[:, ['gt_adj', 'CN', 'AB']].groupby(['gt_adj'])
                covs = gpd[['AB', 'CN']].cov()
                mns = gpd[['AB', 'CN']].mean()
                cts = gpd.size()

    mu_map = {
        1: get_mu_map(1, cts, lambda_0, mu_0, mns),
        2: get_mu_map(2, cts, lambda_0, mu_0, mns),
        3: get_mu_map(3, cts, lambda_0, mu_0, mns)
        }
    sigma_map = {
        1: get_sigma_map(1, cts, lambda_0, psi, covs, mns, mu_0),
        2: get_sigma_map(2, cts, lambda_0, psi, covs, mns, mu_0),
        3: get_sigma_map(3, cts, lambda_0, psi, covs, mns, mu_0)
        }

    df.loc[:, 'lld1'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[1],
        cov=sigma_map[1]
        )
    df.loc[:, 'lld2'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[2],
        cov=sigma_map[2]
        )
    df.loc[:, 'lld3'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[3],
        cov=sigma_map[3]
        )
    lld_code = {'lld1': 1, 'lld2': 2, 'lld3': 3}
    lld_labels = ['lld1', 'lld2', 'lld3']
    df.loc[:, 'gt_new'] = df.loc[:, lld_labels].idxmax(1).map(lld_code)
    df.loc[:, 'gq'] = df.loc[:, lld_labels].max(axis=1) - df.loc[:, lld_labels].median(axis=1)
    df.loc[:, 'med_gq'] = df.loc[:, 'gq'].median()
    df.loc[:, 'q10_gq'] = df.loc[:, 'gq'].quantile(0.1)
    return


def re_recluster_DEL(df):
    # Priors
    mu_0 = {
        1: np.array([0.03, 2]),
        2: np.array([0.46, 1.1]),
        3: np.array([0.94, 0.1])
        }
    psi = {
        1: np.matrix('0.00128 -0.00075; -0.00075 1.1367'),
        2: np.matrix('0.013 -0.0196; -0.0196 0.4626'),
        3: np.matrix('0.0046 -0.0112; -0.0112 0.07556')
        }
    lambda_0 = 1

    df.loc[:, 'gt_adj'] = df.loc[:, 'gt_new'].copy()
    # Set anything with AB > 0.1 and CN < 1.5 to het
    df.loc[(df['gt_new'] == 1) & (df['AB'] > 0.1) & (df['CN'] < 1.5), 'gt_adj'] = 2

    gpd = df.loc[:, ['gt_adj', 'CN', 'AB']].groupby(['gt_adj'])
    covs = gpd[['AB', 'CN']].cov()
    mns = gpd[['AB', 'CN']].mean()
    cts = gpd.size()

    mu_map = {
        1: get_mu_map(1, cts, lambda_0, mu_0, mns),
        2: get_mu_map(2, cts, lambda_0, mu_0, mns),
        3: get_mu_map(3, cts, lambda_0, mu_0, mns)
        }
    sigma_map = {
        1: get_sigma_map(1, cts, lambda_0, psi, covs, mns, mu_0),
        2: get_sigma_map(2, cts, lambda_0, psi, covs, mns, mu_0),
        3: get_sigma_map(3, cts, lambda_0, psi, covs, mns, mu_0)
        }

    df.loc[:, 'lld1'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[1],
        cov=sigma_map[1]
        )
    df.loc[:, 'lld2'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[2],
        cov=sigma_map[2]
        )
    df.loc[:, 'lld3'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[3],
        cov=sigma_map[3]
        )
    lld_code = {'lld1': 1, 'lld2': 2, 'lld3': 3}
    lld_labels = ['lld1', 'lld2', 'lld3']
    df.loc[:, 'gt_new_re'] = df.loc[:, lld_labels].idxmax(1).map(lld_code)
    df.loc[:, 'gq_re'] = df.loc[:, lld_labels].max(axis=1) - df.loc[:, lld_labels].median(axis=1)
    df.loc[:, 'med_gq_re'] = df.loc[:, 'gq_re'].median()
    df.loc[:, 'q10_gq_re'] = df.loc[:, 'gq_re'].quantile(0.1)
    return


def re_recluster_DUP(df):
    # Priors
    mu_0 = {
        1: np.array([0.03, 2]),
        2: np.array([0.27, 3]),
        3: np.array([0.45, 4])
        }
    psi = {
        1: np.matrix('0.00128 -0.00075; -0.00075 1.1367'),
        2: np.matrix('0.013 -0.0196; -0.0196 0.4626'),
        3: np.matrix('0.0046 -0.0112; -0.0112 0.07556')
        }
    lambda_0 = 1

    df.loc[:, 'gt_adj'] = df.loc[:, 'gt_new'].copy()
    df.loc[(df['gt_new'] == 1) & (df['AB'] > 0.1) & (df['CN'] > 2.5), 'gt_adj'] = 2

    gpd = df.loc[:, ['gt_adj', 'CN', 'AB']].groupby(['gt_adj'])
    covs = gpd[['AB', 'CN']].cov()
    mns = gpd[['AB', 'CN']].mean()
    cts = gpd.size()

    mu_map = {
        1: get_mu_map(1, cts, lambda_0, mu_0, mns),
        2: get_mu_map(2, cts, lambda_0, mu_0, mns),
        3: get_mu_map(3, cts, lambda_0, mu_0, mns)
        }
    sigma_map = {
        1: get_sigma_map(1, cts, lambda_0, psi, covs, mns, mu_0),
        2: get_sigma_map(2, cts, lambda_0, psi, covs, mns, mu_0),
        3: get_sigma_map(3, cts, lambda_0, psi, covs, mns, mu_0)
        }

    df.loc[:, 'lld1'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[1],
        cov=sigma_map[1]
        )
    df.loc[:, 'lld2'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[2],
        cov=sigma_map[2]
        )
    df.loc[:, 'lld3'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[3],
        cov=sigma_map[3]
        )
    lld_code = {'lld1': 1, 'lld2': 2, 'lld3': 3}
    lld_labels = ['lld1', 'lld2', 'lld3']
    df.loc[:, 'gt_new_re'] = df.loc[:, lld_labels].idxmax(1).map(lld_code)
    df.loc[:, 'gq_re'] = df.loc[:, lld_labels].max(axis=1) - df.loc[:, lld_labels].median(axis=1)
    df.loc[:, 'med_gq_re'] = df.loc[:, 'gq_re'].median()
    df.loc[:, 'q10_gq_re'] = df.loc[:, 'gq_re'].quantile(0.1)
    return


def recluster_DUP(df):
    # Priors
    mu_0 = {
        1: np.array([0.03, 2]),
        2: np.array([0.27, 3]),
        3: np.array([0.45, 4])
        }
    psi = {
        1: np.matrix('0.00128 -0.00075; -0.00075 1.1367'),
        2: np.matrix('0.013 -0.0196; -0.0196 0.4626'),
        3: np.matrix('0.0046 -0.0112; -0.0112 0.07556')
        }
    lambda_0 = 1

    gpd = df.loc[:, ['gtn', 'CN', 'AB']].groupby(['gtn'])
    covs = gpd[['AB', 'CN']].cov()
    mns = gpd[['AB', 'CN']].mean()
    cts = gpd.size()

    df.loc[:, 'gt_adj'] = df.loc[:, 'gtn'].copy()

    mu_map = {
        1: get_mu_map(1, cts, lambda_0, mu_0, mns),
        2: get_mu_map(2, cts, lambda_0, mu_0, mns),
        3: get_mu_map(3, cts, lambda_0, mu_0, mns)
        }
    sigma_map = {
        1: get_sigma_map(1, cts, lambda_0, psi, covs, mns, mu_0),
        2: get_sigma_map(2, cts, lambda_0, psi, covs, mns, mu_0),
        3: get_sigma_map(3, cts, lambda_0, psi, covs, mns, mu_0)
        }

    df.loc[:, 'lld1'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[1],
        cov=sigma_map[1]
        )
    df.loc[:, 'lld2'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[2],
        cov=sigma_map[2]
        )
    df.loc[:, 'lld3'] = multivariate_normal.logpdf(
        df.loc[:, ['AB', 'CN']],
        mean=mu_map[3],
        cov=sigma_map[3])
    lld_code = {'lld1': 1, 'lld2': 2, 'lld3': 3}
    lld_labels = ['lld1', 'lld2', 'lld3']
    df.loc[:, 'gt_new'] = df.loc[:, lld_labels].idxmax(1).map(lld_code)
    df.loc[:, 'gq'] = df.loc[:, lld_labels].max(axis=1) - df.loc[:, lld_labels].median(axis=1)
    df.loc[:, 'med_gq'] = df.loc[:, 'gq'].median()
    df.loc[:, 'q10_gq'] = df.loc[:, 'gq'].quantile(0.1)
    return


def get_mu_map(j, nn, l0, m0, sample_mean):
    new_mu = m0[j]
    if j in nn:
        new_mu = (l0 * m0[j] + nn[j] * sample_mean.loc[j, :].values) / (l0 + nn[j])
    return new_mu


def get_sigma_map(j, nn, l0, psi0, sample_cov, sample_mean, m0):
    new_sig = psi0[j]
    if (j in nn) and nn[j] > 2:
        val = sample_cov.loc[j, :]
        val += l0 * nn[j] / (l0 + nn[j]) * np.outer(sample_mean.loc[j, :] - m0[j], sample_mean.loc[j, :] - m0[j])
        new_sig = val + psi0[j]
    return new_sig


def load_df(var, exclude, sex, batch):
    test_set = list()
    for s in var.sample_list:
        if s in exclude:
            continue
        if s in batch:
            batch_id = batch[s]
        else:
            batch_id = 'None'
        cn = var.genotype(s).get_format('CN')
        if (var.chrom == 'X' or var.chrom == 'Y') and sex[s] == 1:
            cn = str(float(cn)*2)
        test_set.append(vcf_rec(
            var.var_id,
            s,
            var.info['SVTYPE'],
            var.info['AF'],
            var.genotype(s).get_format('GT'),
            cn,
            var.genotype(s).get_format('AB'),
            batch_id
            ))
    # TODO Check and see if we want to do this as two steps or
    # if it's better to set index at creation
    test_set = pd.DataFrame(data=test_set, columns=vcf_rec._fields)
    return test_set.set_index('batch')


def run_gt_refine(vcf_in, vcf_out, diag_outfile, gender_file, exclude_file, batch_file):

    vcf = Vcf()
    header = []
    in_header = True
    sex = {}

    for line in gender_file:
        v = line.rstrip().split('\t')
        sex[v[0]] = int(v[1])

    exclude = []
    if exclude_file is not None:
        for line in exclude_file:
            exclude.append(line.rstrip())

    batch = dict()
    if batch_file is not None:
        for line in batch_file:
            fields = line.rstrip().split('\t')
            if fields[1] == 'None':
                raise RuntimeError('Batch file contains a batch label of None. This label is reserved.')
            batch[fields[0]] = fields[1]

    outf = open(diag_outfile, 'w', 4096)
    ct = 1

    for line in vcf_in:
        if in_header:
            if line[0] == "#":
                header.append(line)
                continue
            else:
                in_header = False
                vcf.add_header(header)
                vcf.add_info('MEDGQR', '1', 'Float', 'Median quality for refined GT')
                vcf.add_info('Q10GQR', '1', 'Float', 'Q10 quality for refined GT')
                vcf.add_format('GQO', 1, 'Integer', 'Quality of original genotype')
                vcf.add_format('GTO', 1, 'String', 'Genotype before refinement')
                vcf_out.write(vcf.get_header() + '\n')

        v = line.rstrip().split('\t')
        info = v[7].split(';')
        svtype = None
        for x in info:
            if x.startswith('SVTYPE='):
                svtype = x.split('=')[1]
                break
        # bail if not DEL prior to reclassification
        # DUPs can be quite complicated in their allelic structure
        # and thus less amenable to refinement by clustering in many cases
        # INV and BNDs are also unclear.
        # See earlier commits for code of previous attempts to refine these.
        if svtype not in ['DEL', 'MEI']:
            vcf_out.write(line)
            continue

        var = Variant(v, vcf)
        sys.stderr.write("%s\n" % var.var_id)

        sys.stderr.write("%f\n" % float(var.get_info('AF')))
        if float(var.get_info('AF')) < 0.01:
            vcf_out.write(line)
        else:
            df = load_df(var, exclude, sex, batch)
            recdf = recluster(df)
            if ct == 1:
                recdf.to_csv(outf, header=True)
                ct += 1
            else:
                recdf.to_csv(outf, header=False)
            var.set_info("MEDGQR", '{:.2f}'.format(recdf.iloc[0, :].loc['med_gq_re']))
            var.set_info("Q10GQR", '{:.2f}'.format(recdf.iloc[0, :].loc['q10_gq_re']))
            recdf.set_index('sample', inplace=True)
            for s in var.sample_list:
                g = var.genotype(s)
                g.set_format("GTO", g.get_format("GT"))
                g.set_format("GQO", g.get_format("GQ"))
                if s in recdf.index:
                    var.genotype(s).set_format("GT", recdf.loc[s, 'GTR'])
                    var.genotype(s).set_format("GQ", '{:.0f}'.format(recdf.loc[s, 'gq_re']))
                else:
                    var.genotype(s).set_format("GT", "./.")
                    var.genotype(s).set_format("GQ", 0)
            vcf_out.write(var.get_var_string(use_cached_gt_string=False) + '\n')

    vcf_out.close()
    vcf_in.close()
    gender_file.close()
    outf.close()
    if exclude_file is not None:
        exclude_file.close()
    return


def add_arguments_to_parser(parser):
    parser.add_argument('-i', '--input', metavar='<VCF>', dest='vcf_in', default=None, help='VCF input [stdin]')
    parser.add_argument('-o', '--output', metavar='<VCF>', dest='vcf_out', type=argparse.FileType('w'), default=sys.stdout, help='VCF output [stdout]')
    parser.add_argument('-d', '--diag_file', metavar='<STRING>', dest='diag_outfile', type=str, default=None, required=False, help='text file to output method comparisons')
    parser.add_argument('-g', '--gender', metavar='<FILE>', dest='gender', type=argparse.FileType('r'), required=True, default=None, help='tab delimited file of sample genders (male=1, female=2)\nex: SAMPLE_A\t2')
    parser.add_argument('-e', '--exclude', metavar='<FILE>', dest='exclude', type=argparse.FileType('r'), required=False, default=None, help='list of samples to exclude from classification algorithms')
    parser.add_argument('-b', '--batch', metavar='<FILE>', dest='batch', type=argparse.FileType('r'), required=False, default=None, help='tab delimited file of sample batches\nex: SAMPLE_A\tcohort_a')
    parser.set_defaults(entry_point=run_from_args)


def description():
    return 'refine genotypes by clustering'


def command_parser():
    parser = argparse.ArgumentParser(description=description())
    add_arguments_to_parser(parser)
    return parser


def run_from_args(args):
    with su.InputStream(args.vcf_in) as stream:
        run_gt_refine(stream, args.vcf_out, args.diag_outfile, args.gender, args.exclude, args.batch)


if __name__ == '__main__':
    parser = command_parser()
    args = parser.parse_args()
    sys.exit(args.entry_point(args))
