#!/usr/bin/env python3
"""Decompose measured-test errors without changing model predictions.

Test-mean error is a mathematical R2 denominator, not a deployable baseline.
The source/target-training mean is reported separately. No generated rows are
scored, no labels are corrected, and no causal explanation is inferred.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def diagnose(results, out):
    out.mkdir(parents=True, exist_ok=True)
    protocol = json.loads((results / 'protocol.json').read_text())
    observed = pd.read_csv(results / 'observations.csv')
    predictions = pd.read_csv(results / 'observed_predictions.csv')
    metrics = pd.read_csv(results / 'all_metrics.csv')
    manifest = pd.read_csv(results / 'target_fraction_manifest.csv')
    partitions = pd.read_csv(results / 'condition_partition_manifest.csv')
    if set(predictions.kind) != {'measured_endpoint'}:
        raise ValueError('Only measured-endpoint predictions can be diagnosed')
    truth = observed.set_index('record_id')
    if not predictions.record_id.isin(truth.index).all():
        raise ValueError('Unrecognized observation IDs')
    rows = []
    keys = ['seed', 'fold_id', 'held_temperature_C', 'target', 'fraction', 'protocol']
    for values, prediction in predictions.groupby(keys, sort=True):
        metadata = dict(zip(keys, values))
        if prediction.record_id.duplicated().any():
            raise ValueError('Duplicate measured IDs within an evaluation')
        y = truth.loc[prediction.record_id, 'q'].to_numpy(float)
        yp = prediction.predicted_q.to_numpy(float)
        residual = yp - y
        test_mean = float(y.mean())
        sst = float(np.square(y - test_mean).sum())
        sse = float(np.square(residual).sum())
        n = len(y)
        r2 = 1 - sse / sst if sst > 0 else np.nan
        mse = sse / n
        bias = float(residual.mean())
        centered_residual_mse = float(np.square(residual - bias).mean())
        assert np.isclose(mse, bias ** 2 + centered_residual_mse)
        test_population_sd = float(np.std(y, ddof=0))
        if test_population_sd > 0:
            assert np.isclose(r2, 1 - (np.sqrt(mse) / test_population_sd) ** 2)
        selection = manifest[(manifest.seed == metadata['seed']) &
                             (manifest.fold_id == metadata['fold_id']) &
                             (manifest.target == metadata['target']) &
                             (manifest.fraction == metadata['fraction'])]
        train_ids = selection.loc[selection.selected_for_fit, 'record_id']
        train = observed[observed.record_id.isin(train_ids)]
        source_part = partitions[(partitions.fold_id == metadata['fold_id']) &
                                 (partitions.system == 'source') &
                                 (partitions.partition == 'train')]
        source = observed[observed.record_id.isin(source_part.record_id)]
        if train.empty or source.empty:
            raise ValueError('Missing source or target training observations')
        source_t_min, source_t_max = source.temperature_C.min(), source.temperature_C.max()
        target_t_min, target_t_max = train.temperature_C.min(), train.temperature_C.max()
        held = metadata['held_temperature_C']
        row = {
            **metadata,
            'n_test': n,
            'n_target_train': len(train),
            'target_train_temperatures': ';'.join(map(str, sorted(train.temperature_C.unique()))),
            'source_train_temperatures': ';'.join(map(str, sorted(source.temperature_C.unique()))),
            'source_temperature_outside_train_range': not (source_t_min <= held <= source_t_max),
            'target_temperature_outside_train_range': not (target_t_min <= held <= target_t_max),
            'test_response_mean': test_mean,
            'test_response_population_sd': test_population_sd,
            'test_response_min': float(y.min()),
            'test_response_max': float(y.max()),
            'sse_model': sse,
            'sst_test_mean_reference': sst,
            'sse_over_sst': sse / sst if sst > 0 else np.nan,
            'r2_recalculated': r2,
            'rmse_recalculated': float(np.sqrt(mse)),
            'mae_recalculated': float(np.abs(residual).mean()),
            'prediction_bias_mean': bias,
            'bias_squared_fraction_of_mse': bias ** 2 / mse if mse > 0 else np.nan,
            'centered_residual_mse': centered_residual_mse,
            'target_training_mean': float(train.q.mean()),
            'rmse_target_training_mean_baseline': float(np.sqrt(np.square(y - train.q.mean()).mean())),
            'rmse_test_mean_mathematical_reference': test_population_sd,
            'source_pH_constant': source.pH.nunique() == 1,
            'source_pH_values': ';'.join(map(str, sorted(source.pH.unique()))),
            'target_pH_values': ';'.join(map(str, sorted(train.pH.unique()))),
            'negative_q_prediction_count': int((yp < 0).sum()),
            'unit_note': 'q as recorded; units require confirmation',
            'run_purpose': protocol['claims_and_scope']['benchmark_purpose'],
        }
        row['source_pH_outside_train_range'] = bool(
            ((prediction.pH < source.pH.min()) | (prediction.pH > source.pH.max())).any())
        expected = metrics.copy()
        for key, value in metadata.items():
            expected = expected[expected[key] == value]
        if len(expected) != 1:
            raise ValueError('Ambiguous metric row')
        assert np.isclose(row['r2_recalculated'], expected.iloc[0].r2)
        assert np.isclose(row['rmse_recalculated'], expected.iloc[0].rmse)
        assert np.isclose(row['mae_recalculated'], expected.iloc[0].mae)
        rows.append(row)
    diagnostics = pd.DataFrame(rows)
    diagnostics.to_csv(out / 'r2_error_decomposition.csv', index=False)
    sample = diagnostics[np.isclose(diagnostics.fraction, 1.0)]
    columns = ['target', 'protocol', 'n_test', 'r2_recalculated', 'rmse_recalculated',
               'test_response_population_sd', 'prediction_bias_mean', 'sse_over_sst',
               'source_temperature_outside_train_range', 'source_pH_outside_train_range']
    def cell(value):
        if isinstance(value, (float, np.floating)):
            return f'{value:.4f}'
        return str(value).replace('|', '/')
    table = '| ' + ' | '.join(columns) + ' |\n'
    table += '| ' + ' | '.join(['---'] * len(columns)) + ' |\n'
    for values in sample[columns].itertuples(index=False, name=None):
        table += '| ' + ' | '.join(map(cell, values)) + ' |\n'
    purpose = protocol['claims_and_scope']['benchmark_purpose']
    caveat = ('**TESTE DE INTEGRAÇÃO: poucas épocas/sementes. Não interpretar como resultado científico final.**'
              if purpose == 'integration_smoke' else
              '**Avaliação cruzada retrospectiva, não confirmação experimental independente.**')
    text = f'''# Diagnóstico das métricas de endpoints\n\n{caveat}\n\n## Identidade matemática\n\nR² = 1 − SSE/SST, com SSE = Σ(y − ŷ)² e SST = Σ(y − média do teste)².\nO valor negativo indica SSE > SST. A referência da média do teste é usada somente\npara definir R²; ela não seria conhecida ao prever um novo experimento. O baseline\nde média do treino é computado separadamente.\n\nUsando desvio-padrão populacional dos valores do teste:\n\nR² = 1 − (RMSE / SD_teste)².\n\nPortanto, erro absoluto aparentemente moderado pode produzir R² muito negativo\nquando a variabilidade do teste é pequena. Isso não torna o erro irrelevante nem\na previsão adequada. RMSE e MAE devem acompanhar R², sempre com os valores\nmedidos e o número de condições.\n\nMSE também é decomposto em viés² + variância populacional dos resíduos. Essa\ndecomposição identifica erro sistemático e dispersão; não identifica sua causa\nquímica nem determina se os dados são verdadeiros ou falsos.\n\n## Exemplo: fração nominal de treino 100%\n\n{table}\n\nAs temperaturas fora da faixa e o pH fora da faixa da fonte são fatos registrados\npelo desenho do teste. São dificuldades plausíveis de generalização, mas atribuir\na elas causalmente as discrepâncias exige controles adicionais. O treinamento\ncom apenas dois níveis de temperatura e poucos endpoints limita a informação\ndisponível. A ambiguidade de unidade e a ausência dos controles não são resolvidas\npelo desempenho numérico do algoritmo.\n\nA regressão Ridge possui forma e otimização diferentes das redes; no smoke ela\npode estar ajustada enquanto as redes pararam após duas épocas. Não usar esse\nresultado para concluir superioridade geral nem para eliminar comparações.\n\nNão ajustar novos modelos, selecionar sementes ou alterar a regra de retenção\nde temperaturas com base neste relatório e chamar a nova avaliação de intocada.\n'''
    (out / 'Diagnostico_R2.md').write_text(text, encoding='utf-8')
    print(f'Created diagnostics for {len(diagnostics)} measured evaluations at {out}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    diagnose(args.results, args.out)


if __name__ == '__main__':
    main()
